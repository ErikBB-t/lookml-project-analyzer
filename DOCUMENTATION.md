# Technical Documentation - LookML Structure Analyzer

This file provides a detailed technical overview of how `app.py` works internally to analyze LookML projects.

## Overview

The main goal of the script is to deconstruct LookML models to create an explicit link between "explores," "joins," and the underlying "views." This is information that is not easily accessible in the Looker UI but is critical for understanding dependencies, cleaning up code, and analyzing project structure.

The analysis is tailored for standard LookML syntax and project structure (`views` and `models` folders).

## File Structure

-   `app.py`: The main file containing all the logic for the Streamlit interface and the LookML parser.
-   `list_used_views.py`: The original standalone script. Its functionality is now integrated directly into `app.py`.
-   `requirements.txt`: Defines the Python dependencies (Streamlit and Pandas).
-   `README.md`: General user guide.
-   `DOCUMENTATION.md`: This file.

## Core Logic: Parsing Process

The parsing logic is a series of functions that work together to read and interpret LookML code. Since LookML is a proprietary format without a standardized parser (like a JSON parser), the logic is based on a combination of file system operations and regular expressions.

### 1. `map_views_to_folders(views_dir)`

-   **Purpose:** Before we can analyze the models, we need to know where all available "views" are located. This function creates a mapping between a view name and the folder it resides in.
-   **Process:**
    1.  Takes the path to the `views` folder in a cloned repo.
    2.  Recursively goes through all subfolders and files.
    3.  For each file ending in `.view.lkml`, the view name is extracted from the filename.
    4.  The folder name directly under `views` is identified as "View Folder."
    5.  Returns a dictionary, e.g., `{ "orders": "core", "users": "core", "products": "ecommerce" }`.

### 2. Text Processing

LookML files are read as plain text. Before they can be analyzed, they need to be cleaned up.

-   **`strip_lookml_comments(text)`**: Uses a simple regular expression (`#.*`) to remove all comments. This simplifies the subsequent parsing process.

### 3. Block Analysis

LookML is structured in blocks with curly braces (`{}`). The code must be able to identify these to isolate `explore` and `join` definitions.

-   **`find_matching_brace(text, open_brace_index)`**: A helper function that finds the corresponding closing brace `}` for a given opening brace `{`. It keeps track of the depth to handle nested blocks correctly.
-   **`extract_named_blocks(text, keyword)`**:
    -   **Purpose:** This is a key function that finds all named blocks of a specific type (e.g., `explore` or `join`).
    -   **Process:**
        1.  Uses a regular expression to find the pattern `<keyword>: <name> {`.
        2.  When it finds a match, it stores the name (e.g., `explore_name`).
        3.  It calls `find_matching_brace` to find the end of the block.
        4.  The entire content between `{` and `}` is extracted as the "body."
        5.  Returns a list of dictionaries, each with `name` and `body`.

### 4. `parse_explore_usage(model_content)`

-   **Purpose:** This is the orchestration function for analyzing the content of a single model file.
-   **Process:**
    1.  Runs `strip_lookml_comments` on the file content.
    2.  Calls `extract_named_blocks` with `keyword="explore"` to get a list of all explores in the file.
    3.  For each `explore`:
        a.  **Primary View:** It is first assumed that the view name is the same as the explore name. Then, it checks for a `from:` or `view_name:` parameter inside the explore block using `parse_view_override`. This provides the actual view name.
        b.  A row is added for the primary view.
        c.  **Joins:** Then, `extract_named_blocks` is called again, this time on the `explore` block's content with `keyword="join"`.
        d.  For each `join`, the same logic as in (a) is repeated to find the actual view name for the join.
        e.  A row is added for each join.
    4.  Returns a list of rows, where each row is a dictionary representing a view usage (either as a primary view or a join view).

### 5. `analyze_repo(repo_path)` (Streamlit Integration)

-   **Purpose:** Binds everything together and runs the entire analysis on a cloned repository.
-   **Process:**
    1.  Identifies the `views` and `models` folders based on the repo path.
    2.  Calls `map_views_to_folders` to build the view-folder overview.
    3.  Iterates through all `.model.lkml` files.
    4.  For each file, `parse_explore_usage` is called.
    5.  The results from `parse_explore_usage` are combined with the information from `map_views_to_folders` to create complete rows.
    6.  All rows are collected and converted into a Pandas DataFrame, which is returned to the Streamlit app for display.

## Handling GitHub Repo

-   **Temporary Folder:** The app uses Python's `tempfile` module to create a unique, temporary folder for each repo to be analyzed.
-   **Cloning:** A `git clone` command is run as a subprocess to download the repo into the temporary folder.
-   **Cleanup:** A `finally` block ensures that the temporary folder and all its contents are deleted after the analysis is complete (or if an error occurs), to prevent the disk from filling up.
