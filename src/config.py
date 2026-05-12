import os
import getpass

# Filtering Config
DEGENERATE_STEREOTYPES = {'incidental', 'empty', 'stateless'}
IGNORED_NON_DEGENERATE_STEREOTYPES = {"destructor", "copy-constructor", "constructor"}
SPECIFIERS = {'virtual', 'override', 'abstract'}
STANDARD_OVERRIDES = {"ToString", "Equals", "GetHashCode", "Dispose", "Clone", "CompareTo", "GetEnumerator"}
INSTANCE_ATTRIBUTES = {
    # Test Frameworks (CA1822 explicitly ignores tests)
    'test', 'setup', 'teardown', 'fact', 'testmethod', 'testinitialize', 'testcleanup', 'testcase', 'theory', 'property',
    
    # BenchmarkDotNet (BDN requires instances to compile generated code)
    'benchmark', 'globalsetup', 'globalcleanup', 'iterationsetup', 'iterationcleanup', 'argumentssource'
}

EVENT_HANDLER_SENDERS = ["object ", "object? "]
EVENT_HANDLER_ARGS = ["eventargs"]
EVENT_HANDLER_SUFFIXES = ("_click", "_load")


# Output Config
HEADER = ["method_name", "line_number", "file_name", "to_static", "reasoning"]
#GEMINI_MODEL = "gemini-3.1-pro-preview"
GEMINI_MODEL = "gemini-3-flash-preview"
# GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
if "GOOGLE_API_KEY" not in os.environ: os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter your Google AI API key: ")
TOKEN_SAFETY_MARGIN = 0.5

# Prompt Config
SYSTEM_PROMPT = """
### CONTEXT
You are a C# expert.
Determine if the given class is implementing a method in an external interface

### INPUT
* type_name: The name of the class/struct.
* type_file_name: The file name where the type is defined.
* type_parent_names: A list of base type names that the current type inherits from.
* methods: A list of methods in this type to evaluate (see below).

METHOD STRUCTURE ('methods'):
* method_name: The name of the method.
* method_line_number: The line number where the method is defined inside 'type_file_name'.
* method_specifiers: Access specifiers/modifiers.
* method_return_type: The complete return type.
* method_parameters: The raw parameters string.

### TASK
Follow these STRICT rules to output `requires_instance_context`:
1. `requires_instance_context: TRUE`: If the method is implementing a method in one of its `type_parent_names`.
Example: `Run` for `IBackgroundTask` --> Requires instance context because it is an implementation of a method in a common Microsoft interface.
2. `requires_instance_context: FALSE`: Otherwise
"""
