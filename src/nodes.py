import csv
import json
import os
import src.helpers
from google import genai
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from .state import AgentState, CandidateMethod, LLMOutputModel
from .config import DEGENERATE_STEREOTYPES, IGNORED_NON_DEGENERATE_STEREOTYPES, SYSTEM_PROMPT, GEMINI_MODEL, TOKEN_SAFETY_MARGIN, HEADER


# In C#, if a class overrides a method from a base class (direct or indirect), it must use the override keyword
# We have already caught all of those cases deterministically!
# The only time a method fulfills an inheritance contract without the override keyword is when it implements an interface
# And a class must explicitly list the interfaces it implements directly
# Therefore, passing indirect parents just wastes tokens and confuses the LLM, and as such, we do not use them
#
def direct_candidates_analysis(state: AgentState) -> AgentState:
    print ("--- Starting Direct Candidates Analysis ---")

    llm_input = []
    cascading_input = []
    direct_candidates = []
    direct_rejected = []

    with open(state['input_file_path'], 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            type_name = row.get('type_name')
            method_name = row.get('function_name')
            method_stereotypes = src.helpers.parse_csv_list(row.get('function_stereotype'))

            if row.get('function_unit_language') != "C#":
                continue
            if type_name == "N/A" or method_name == "N/A":
                continue
            if method_name in {"get", "set"}: # Do not use lower() as regular methods can be called as Get() or Set()
                continue
            if any(s in IGNORED_NON_DEGENERATE_STEREOTYPES for s in method_stereotypes):
                continue

            candidate = CandidateMethod(
                type_name=type_name,
                type_file_name=row.get('type_file_name'),
                type_parent_names=list(src.helpers.parse_csv_list(row.get('type_parents'))),
                type_inherited_parent_names=list(src.helpers.parse_csv_list(row.get('type_inherited_parents'))),
                type_function_signatures=list(src.helpers.parse_csv_list(row.get('type_function_signatures'))),
                type_inherited_function_signatures=list(src.helpers.parse_csv_list(row.get('type_inherited_function_signatures'))),
                method_name=method_name,
                method_line_number=row.get('function_line_number'),
                method_attributes=list(src.helpers.parse_csv_list(row.get('function_attributes'))),
                method_parameters=row.get('function_parameters_list'),
                method_return_type=row.get('function_return_type'),
                method_specifiers=list(src.helpers.parse_csv_list(row.get('function_specifiers'))),
                method_signature=row.get('function_signature'),
                method_stereotypes = method_stereotypes,
                method_internal_calls=list(src.helpers.parse_csv_list(row.get('function_internal_calls'))),   
                method_external_calls=list(src.helpers.parse_csv_list(row.get('function_external_calls'))),   
            )
            method_is_field_used = src.helpers.parse_bool(row.get('function_fields_modified')) or src.helpers.parse_bool(row.get('function_calls_on_fields')) or src.helpers.parse_bool(row.get('function_field_used'))

            # Basic filtered for simple cases
            if src.helpers.cannot_be_converted_to_static(candidate) or method_is_field_used:
                direct_rejected.append(candidate)
            else:
                method_is_degenerate = any(s in DEGENERATE_STEREOTYPES for s in candidate.method_stereotypes)
                type_has_unknown_parent = src.helpers.parse_bool(row.get('type_unknown_parents'))

                # A lot of the external calls come from types that have unknown parents. 
                # Therefore, for types with known parents, we can assume that the external calls are made to Static data members and is a safe assumption 
                if type_has_unknown_parent: # Those need an LLM (not defined in source code)
                    llm_input.append(candidate)
                elif method_is_degenerate:
                    direct_candidates.append(candidate) # Degenerate methods (no field usage, no internal calls)
                elif candidate.method_internal_calls: # Non-degenerate methods (no field usage, but has internal calls like a command, and possibly internal calls)
                    cascading_input.append(candidate)
                # This will never be true. Commented out for future notes. Getting here means no field usage, no internal calls, and is not a degenerate, which is not possible because those are always degenerate by definition.
                else:
                    cascading_input.append(candidate)
                
    print(f"Total Methods (After Filtering): {len(direct_candidates) + len(llm_input) + len(direct_rejected) + len(cascading_input)}")
    print(f"  - Direct Candidates (Accepted): {len(direct_candidates)}")
    print(f"  - Direct Candidates (Rejected): {len(direct_rejected)}")
    print(f"  - LLM Input: {len(llm_input)}")
    print(f"  - Cascading Input: {len(cascading_input)}")

    return {
        "llm_input": llm_input,
        "direct_candidates": direct_candidates,
        "direct_rejected": direct_rejected,
        "cascading_input": cascading_input
    }

def llm_analysis(state: AgentState):
    llm_input = state['llm_input']
    if len(llm_input) == 0:
        print("--- No LLM Analysis Needed ---")
        return {"llm_candidates": []}

    print(f"--- Executing LLM ({len(llm_input)} items) ---")

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    model_info = client.models.get(model=GEMINI_MODEL)
    token_budget = int(model_info.output_token_limit * TOKEN_SAFETY_MARGIN)
    print(f"  [Token Budget] {token_budget} tokens (based on {TOKEN_SAFETY_MARGIN*100}% of {model_info.output_token_limit})")

    grouped_data = {}
    for item in llm_input:
        key = (item.type_name, item.type_file_name, tuple(item.type_parent_names))
        if key not in grouped_data:
            grouped_data[key] = {
                "type_name": item.type_name,
                "type_file_name": item.type_file_name,
                "type_parent_names": list(set(item.type_parent_names).union(item.type_inherited_parent_names)),
                "methods": []
            }

        method_dict = item.model_dump(exclude={
            'type_name', 'type_file_name', 'type_parent_names', 'type_inherited_parent_names', 'method_signature', 'type_function_signatures', 'type_inherited_function_signatures',
            'method_internal_calls', 'method_external_calls',  'method_stereotypes', 'method_attributes'
        })
        grouped_data[key]["methods"].append(method_dict)

    all_data = list(grouped_data.values())
    total_batch_tokens = client.models.count_tokens(model=GEMINI_MODEL, contents=json.dumps(all_data)).total_tokens
    avg_tokens_per_item = total_batch_tokens / len(all_data)
    if avg_tokens_per_item < 1: avg_tokens_per_item = 1 # Avoid division by zero if something weird happens
    chunk_size = int(token_budget / avg_tokens_per_item)
    if chunk_size < 1: chunk_size = 1
    print(f"  [Chunking] Total Tokens: {total_batch_tokens} | Avg/Item: {avg_tokens_per_item:.1f} | Batch Size: {chunk_size}")
    chunks = [all_data[i: i + chunk_size] for i in range(0, len(all_data), chunk_size)]
    print(f"  [Chunking] Created {len(chunks)} chunks based on token budget.")

    # Process Chunks
    base_llm = ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,         
        thinking_level="low",         # Active reasoning
        temperature=0.0,              # No randomness
        top_k=1,                      # Only the single most likely token is allowed
    )
    
    structured_llm = base_llm.with_structured_output(schema=LLMOutputModel, method="json_schema")
    raw_llm_candidates = []
    for i, chunk in enumerate(chunks):
        methods_in_chunk = sum(len(type_group["methods"]) for type_group in chunk) # Count the actual methods inside the grouped Type dictionaries for this chunk
        print(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} types containing {methods_in_chunk} methods)...")
        chunk_json = json.dumps(chunk)
        user_msg = f"Here is a batch of {methods_in_chunk} methods to analyze.\nDATA:\n{chunk_json}"
        response = structured_llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_msg)
        ])
        if response and response.results:
            raw_llm_candidates.extend(response.results)
        else: 
            print(f"Warning: Chunk {i} returned no structured results.")
    
    # We remove any result the LLM hallucinated that does not exist in the input
    valid_keys = {(c.method_name, c.method_line_number, c.type_file_name) for c in llm_input}
    llm_candidates = [c for c in raw_llm_candidates if (c.method_name, c.method_line_number, c.type_file_name) in valid_keys]
    llm_unknown = sum(1 for c in llm_candidates if not c.requires_instance_context)
    llm_rejected = len(llm_candidates) - llm_unknown
    
    print(f"  - LLM Candidates (Unknown): {llm_unknown}")
    print(f"  - LLM Candidates (Rejected): {llm_rejected}")
    if len(raw_llm_candidates) != len(llm_candidates):
        print(f"  - [Warning] Removed {len(raw_llm_candidates) - len(llm_candidates)} hallucinated results.")
    
    return {"llm_candidates": llm_candidates}

# Two-stage cascading validation:
def cascading_candidates_analysis(state: AgentState):
    print("--- Resolving Dependencies (Cascading Analysis) ---")
 
    # Seed the approved set with direct candidates (file-scoped to prevent cross-file collisions)
    approved_scoped_methods = set()
    for c in state['direct_candidates']:
        approved_scoped_methods.add(c.method_signature)
 
    # cascading_input goes straight to Stage 2 — external calls already cleared in direct_candidates_analysis
    pending_cascading = list(state['cascading_input'])
    cascading_candidates = []
    cascading_rejected  = []
 
    # --- STAGE 1: Pre-filter LLM-FALSE methods by call profile ---
    if state['llm_candidates']:
        llm_input_mapping = {
            (c.method_name, c.method_line_number, c.type_file_name): c
            for c in state['llm_input']
        }
 
        tier1_approved  = tier2_queued = 0
 
        for llm_result in state['llm_candidates']:
            if not llm_result.requires_instance_context:
                candidate = llm_input_mapping[(llm_result.method_name, llm_result.method_line_number, llm_result.type_file_name)]

                # Tier 1: No internal calls, no field usage, no unknown parents, and maybe external calls — Most likely to be truly static, approve
                if not candidate.method_internal_calls:
                    cascading_candidates.append(candidate)
                    approved_scoped_methods.add(candidate.method_signature)
                    tier1_approved += 1

                # Tier 2: Has internal calls, no field usage, no unknown parents, and maybe external calls —  Queue for Stage 2 to analyze the internal calls
                else:
                    pending_cascading.append(candidate)
                    tier2_queued += 1
        
        print(f"  - Stage 1 | Tier 1 (no internal calls, approved):          {tier1_approved}")
        print(f"  - Stage 1 | Tier 2 (internal calls, queued):               {tier2_queued}")
 
    print(f"  - Stage 2 | Methods entering dependency loop:      {len(pending_cascading)}")
 
    # --- STAGE 2: Dependency Resolution Loop ---
    # A method is safe only when every internal call it makes is already in the approved set.
    # Tier 1/2 approvals above have already expanded approved_scoped_methods, so they
    # can serve as satisfied dependencies for methods resolved here.
    while True:
        newly_approved_in_this_pass = 0
        still_pending = []
 
        for candidate in pending_cascading:
            is_safe = True
            for call in candidate.method_internal_calls:
                if call not in approved_scoped_methods:
                    is_safe = False
                    break
 
            if is_safe:
                cascading_candidates.append(candidate)
                approved_scoped_methods.add(candidate.method_signature)
                newly_approved_in_this_pass += 1
            else:
                still_pending.append(candidate)
 
        pending_cascading = still_pending
        if newly_approved_in_this_pass == 0:
            break
 
    cascading_rejected.extend(pending_cascading)
 
    print(f"  - Stage 2 | Cascading Approved:                    {len(cascading_candidates)}")
    print(f"  - Stage 2 | Cascading Rejected:                    {len(cascading_rejected)}")
 
    return {
        "cascading_candidates": cascading_candidates,
        "cascading_rejected": cascading_rejected,
        "llm_candidates": state['llm_candidates']
    }

def output(state: AgentState):
    print("--- Exporting Results ---")
    output_path = state['output_file_path'] 
    
    # Create a fast lookup set for methods that were routed to the LLM stage
    llm_input_keys = {
        (c.method_name, str(c.method_line_number), c.type_file_name) 
        for c in state['llm_input']
    }
    
    with open(output_path, "w", encoding="utf-8", newline='') as file_out:
        csv_writer = csv.writer(file_out)
        csv_writer.writerow(HEADER)

        for c in state['direct_candidates']:
            csv_writer.writerow([c.method_name, c.method_line_number, c.type_file_name, True, "Direct Analysis"])
            
        for c in state['direct_rejected']:
            csv_writer.writerow([c.method_name, c.method_line_number, c.type_file_name, False, "Direct Analysis"])

        for c in state['llm_candidates']:
            # ONLY print the ones rejected by the LLM here, so we get their LLM reasoning.
            if c.requires_instance_context: 
                csv_writer.writerow([c.method_name, c.method_line_number, c.type_file_name, False, c.reasoning])

        for c in state['cascading_candidates']:
            key = (c.method_name, str(c.method_line_number), c.type_file_name)
            
            # Determine the exact path the method took to get approved
            if key in llm_input_keys:
                if not c.method_internal_calls:
                    reasoning = "Cascading + LLM (No Internal Calls)"
                else:
                    reasoning = "Cascading + LLM (With Internal Calls)"
            else:
                reasoning = "Cascading Analysis"
                
            csv_writer.writerow([c.method_name, c.method_line_number, c.type_file_name, True, reasoning])

        for c in state['cascading_rejected']:
            key = (c.method_name, str(c.method_line_number), c.type_file_name)
            
            # Apply the same labeling logic so rejections are also clearly tracked
            if key in llm_input_keys:
                reasoning = "Cascading + LLM (With Internal Calls)"
            else:
                reasoning = "Cascading Analysis"
                
            csv_writer.writerow([c.method_name, c.method_line_number, c.type_file_name, False, reasoning])

    print(f"Export complete: {output_path}")
    return {}
