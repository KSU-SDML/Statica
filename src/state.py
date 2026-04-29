from typing import TypedDict, List
from pydantic import BaseModel, Field

class CandidateMethod(BaseModel):
    type_name: str # Type (e.g., class) where method resides
    type_file_name: str # Type file name/path
    type_parent_names: List[str] # Type parent names
    type_inherited_parent_names: List[str] # Type inherited parent names
    type_function_signatures: List[str] = [] # Type function signatures
    type_inherited_function_signatures: List[str] = [] # Type inherited function signatures
    method_name: str # Method name
    method_line_number: str # Method line number
    method_attributes: List[str] # Method attributes (e.g., [Test])
    method_parameters: str # Method parameters (e.g., (int x, string y))
    method_return_type: str # Method return type (e.g., int)
    method_specifiers: List[str] # Method specifiers (e.g., virtual)
    method_signature: str # Method signature (e.g., void Foo(,))
    method_stereotypes: List[str] # Method stereotypes (e.g., incidental)
    method_internal_calls: List[str] = [] # Method calls to other methods in type
    method_external_calls: List[str] = [] # Method calls to external methods

class LLMOutput(BaseModel):
    type_file_name: str
    method_name: str 
    method_line_number: str
    reasoning: str # For chain-of-thought explanations
    requires_instance_context: bool

class LLMOutputModel(BaseModel):
    results: list[LLMOutput] = Field()

class AgentState(TypedDict):
    input_file_path: str # Input file (CSV format from Stereocode)
    output_file_path: str # Output file (CSV format for Statica)
    direct_candidates: List[CandidateMethod] # Candidate methods confirmed deterministically 
    direct_rejected: List[CandidateMethod] # Candidate methods rejected deterministically
    cascading_input: List[CandidateMethod] # Cascading candidate methods to be analyzed
    cascading_candidates: List[CandidateMethod] # Cascading candidate methods confirmed deterministically
    cascading_rejected: List[CandidateMethod] # Cascading candidate methods rejected deterministically
    llm_input: List[CandidateMethod] # Candidate methods to be passed to the LLM
    llm_candidates: List[LLMOutput] # Candidate methods confirmed by the LLM
