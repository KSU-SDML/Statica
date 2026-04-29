import csv
import sys
from .config import SPECIFIERS, INSTANCE_ATTRIBUTES, STANDARD_OVERRIDES, EVENT_HANDLER_SUFFIXES, EVENT_HANDLER_SENDERS, EVENT_HANDLER_ARGS

maxInt = sys.maxsize
csv.field_size_limit(maxInt)

def parse_csv_list(text, delimiter=' '):
    """ 
    Parses a string into a set of items based on a specified delimiter.
    Safely ignores delimiters that appear inside parentheses () or brackets [].
    If the input is "N/A" or empty, it returns an empty set. 
    """
    if text == "N/A" or not text: 
        return set()

    items = set()
    current_item = []
    paren_depth = 0
    bracket_depth = 0

    for char in text:
        if char == '(': paren_depth += 1
        elif char == ')': paren_depth -= 1
        elif char == '[': bracket_depth += 1
        elif char == ']': bracket_depth -= 1

        # Only split if we hit the delimiter AND we are not inside () or []
        if char == delimiter and paren_depth == 0 and bracket_depth == 0:
            if current_item:  # Avoid adding empty strings from double spaces
                items.add(''.join(current_item).strip())
            current_item = []
        else:
            current_item.append(char)

    # Catch the last item
    if current_item:
        items.add(''.join(current_item).strip())

    return items

def parse_bool(text):
    """ Parses a string into a boolean. It returns True if the string is "true" (case-insensitive), and False otherwise. """

    return str(text).lower().strip() == 'true'

def cannot_be_converted_to_static(candidate):
    """Determines if a method cannot be converted to static based on its specifiers, inheritance, name, parameters, and attributes."""

    # 1. Standard Specifiers
    if set(candidate.method_specifiers) & SPECIFIERS:
        return True
    
    # 2. Known Internal Inheritance
    if candidate.method_signature in candidate.type_inherited_function_signatures:
        return True
        
    # 3. Standard C# Overrides
    if candidate.method_name in STANDARD_OVERRIDES:
        return True
        
    # 4. Standard Event Handlers / UI Triggers
    # Examples:
    # object sender, EventArgs e
    # Object Sender, EventArgs eventArgs
    # System.Object s, System.EventArgs args
    params_lower = candidate.method_parameters.lower()
    method_name_lower = candidate.method_name.lower()
    if any(sender in params_lower for sender in EVENT_HANDLER_SENDERS) and any(arg in params_lower for arg in EVENT_HANDLER_ARGS):
        return True
    if method_name_lower.endswith(EVENT_HANDLER_SUFFIXES):
        return True
    
    # 5. Reflection/Framework Attributes
    for raw_attribute in candidate.method_attributes:
        # Step 1: Remove the outer brackets and lowercase
        clean_attr_string = raw_attribute.strip('[]').lower()
        
        # Step 2: Safely split stacked attributes by comma (ignoring commas inside parens)
        safe_attributes = []
        current_attr = []
        paren_depth = 0
        
        for char in clean_attr_string:
            if char == '(': paren_depth += 1
            elif char == ')': paren_depth -= 1
            
            # If we hit a comma and we are NOT inside a parenthesis, split here
            if char == ',' and paren_depth == 0:
                safe_attributes.append(''.join(current_attr).strip())
                current_attr = []
            else:
                current_attr.append(char)
                
        # Catch the final attribute in the string
        if current_attr:
            safe_attributes.append(''.join(current_attr).strip())
            
        # Step 3: Now that they are safely separated, strip parameters and check
        for attr in safe_attributes:
            base_attr_name = attr.split('(')[0].strip()
            
            if base_attr_name in INSTANCE_ATTRIBUTES:
                return True

    return False
