import os
import glob
import logging
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, List, Any

# Configure logging for this module
logger = logging.getLogger(__name__)

def execute_plot_code(code_string: str, plot_data: Dict[str, Any]) -> List[str]:
    """
    Safely executes AI-generated Python code intended to create matplotlib plots.

    Args:
        code_string: A string containing the Python code to execute.
        plot_data: A dictionary containing the data variables the code expects
                   (e.g., {'assignee_workload_dict': {...}, 'state_counts_dict': {...}}).

    Returns:
        A list of file paths for the successfully generated plot images (.png).
        Returns an empty list if execution fails or no plots are saved.
    """
    plot_dir = "./data/plots"
    generated_files = []

    # --- REMOVED PLOT CLEARING LOGIC --- 
    # The caller (run_report.py) should handle directory setup and clearing once before the loop.

    # Prepare the restricted execution environment
    # Only allow specific modules and the provided data variables
    allowed_globals = {
        # '__builtins__': {}, # REMOVED: Allow standard builtins for compatibility with import etc.
        'pd': pd,
        'plt': plt,
        # Add specific data variables from plot_data - names MUST match the AI prompt
        'assignee_workload_dict': plot_data.get('assignee_workload_dict', {}),
        'state_counts_dict': plot_data.get('state_counts_dict', {}),
        'recent_activity_metrics': plot_data.get('recent_activity_metrics', {}),
        'overall_metrics': plot_data.get('overall_metrics', {})
        # Add other necessary data variables here if the prompt requires them
    }
    # Standard builtins like print, dict, list, range will now be available by default.

    # 3. Execute the code string within the restricted environment
    logger.debug(f"Attempting to execute code:\n---\n{code_string[:500]}...\n---") # Log start of code
    try:
        # Execute the code. Using globals=allowed_globals restricts the available variables/modules.
        # locals={} provides an empty local scope.
        exec(code_string, allowed_globals, {})
        logger.info("Successfully executed AI-generated plot code block.")

        # 4. Collect newly generated plot files
        generated_files = glob.glob(os.path.join(plot_dir, 'plot_*.png')) # Match the naming convention
        logger.info(f"Found {len(generated_files)} plot file(s) after execution: {generated_files}")

    except SyntaxError as e:
        logger.error(f"Syntax Error in generated code: {e}", exc_info=True)
        logger.error(f"Failed code snippet:\n{code_string}")
    except NameError as e:
         logger.error(f"Name Error in generated code (likely missing import or undefined variable): {e}", exc_info=True)
         logger.error(f"Failed code snippet:\n{code_string}")
    except ImportError as e:
         logger.error(f"Import Error in generated code: {e}", exc_info=True)
         logger.error(f"Failed code snippet:\n{code_string}")
    except FileNotFoundError as e: # Catch errors if plt.savefig fails
         logger.error(f"File Not Found Error during plot saving: {e}", exc_info=True)
         logger.error(f"Failed code snippet:\n{code_string}")
    except TypeError as e:
         logger.error(f"Type Error in generated code (often data mismatch): {e}", exc_info=True)
         logger.error(f"Failed code snippet:\n{code_string}")
    except ValueError as e:
         logger.error(f"Value Error in generated code: {e}", exc_info=True)
         logger.error(f"Failed code snippet:\n{code_string}")
    except Exception as e:
        # Catch any other unexpected errors during execution
        logger.error(f"An unexpected error occurred during plot code execution: {e}", exc_info=True)
        logger.error(f"Failed code snippet:\n{code_string}")

    return generated_files # Return list of found plot files (empty if execution failed) 