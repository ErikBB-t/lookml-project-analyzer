import streamlit as st
import os
import re
import pandas as pd
import tempfile
import shutil
import subprocess
from collections import defaultdict
from functools import lru_cache

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="LookML Project Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Core Parsing and Analysis Functions ---

def map_views_to_metadata(views_dir: str) -> tuple[dict, list]:
    """
    Scans the /views directory to map each view name to its metadata.
    Returns a tuple:
    - (dict): A map of `view_name -> {'folder': str, 'path': str}`.
    - (list): A list of file paths that contain more than one view definition.
    """
    view_metadata_map = {}
    files_with_multiple_views = []

    if not os.path.isdir(views_dir):
        return view_metadata_map, files_with_multiple_views

    view_name_pattern = re.compile(r"^\s*view:\s*([a-zA-Z0-9_]+)", re.MULTILINE)

    for root, _, files in os.walk(views_dir):
        for file in files:
            if file.endswith(".view.lkml"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    found_views = view_name_pattern.findall(content)

                    if len(found_views) > 1:
                        relative_path = os.path.relpath(file_path, views_dir)
                        files_with_multiple_views.append(relative_path)

                    if not found_views:
                        found_views.append(file.replace(".view.lkml", ""))

                    relative_dir = os.path.relpath(root, views_dir)
                    folder = relative_dir.split(os.sep)[0] if relative_dir and relative_dir != "." else "(root)"

                    for view_name in found_views:
                        view_metadata_map[view_name] = {"folder": folder, "path": file_path}

                except Exception:
                    continue

    return view_metadata_map, files_with_multiple_views


def strip_lookml_comments(text: str) -> str:
    return re.sub(r"#.*", "", text)


def find_matching_brace(text: str, open_brace_index: int) -> int:
    depth = 0
    for i in range(open_brace_index, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_named_blocks(text: str, keyword: str) -> list:
    blocks = []
    pattern = re.compile(rf"\b{re.escape(keyword)}\s*:\s*([a-zA-Z0-9_]+)\s*\{{")
    for m in pattern.finditer(text):
        name, open_brace_index = m.group(1), m.end() - 1
        close_brace_index = find_matching_brace(text, open_brace_index)
        if close_brace_index != -1:
            body = text[open_brace_index + 1 : close_brace_index]
            blocks.append({"name": name, "body": body})
    return blocks


@lru_cache(maxsize=None)
def get_view_description_coverage(view_path: str) -> float | None:
    """
    Calculates the percentage of fields (dimensions, measures) with descriptions in a view file.
    Caches the result to avoid re-reading and re-parsing the same file.
    """
    if not view_path or not os.path.exists(view_path):
        return None
    
    try:
        with open(view_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    uncommented_content = strip_lookml_comments(content)
    
    dimensions = extract_named_blocks(uncommented_content, "dimension")
    measures = extract_named_blocks(uncommented_content, "measure")
    
    total_fields = len(dimensions) + len(measures)
    if total_fields == 0:
        return 1.0  # Or 0.0, depending on how we want to treat empty views. 1.0 implies "100% compliant".

    fields_with_description = 0
    for field in dimensions + measures:
        if "description:" in field["body"]:
            fields_with_description += 1
            
    return fields_with_description / total_fields


def _has_primary_key(view_content: str) -> bool:
    """Checks if a view's content has a dimension with primary_key: yes."""
    uncommented_content = strip_lookml_comments(view_content)
    dimensions = extract_named_blocks(uncommented_content, "dimension")
    for dim in dimensions:
        if "primary_key: yes" in dim["body"]:
            return True
    return False


def analyze_repo(repo_path: str):
    """
    Performs a deep analysis of a LookML repository.
    """
    views_dir = os.path.join(repo_path, "views")
    models_dir = os.path.join(repo_path, "models")

    if not os.path.isdir(models_dir):
        st.error("The 'models' directory was not found. Please ensure this is a standard LookML project.")
        return None, {}

    view_metadata, files_with_multiple_views = map_views_to_metadata(views_dir)
    get_view_description_coverage.cache_clear()  # Clear cache for each new analysis

    structure_rows = []
    views_without_pk = set()
    total_explores, explores_with_desc = 0, 0
    total_joins, joins_with_desc = 0, 0
    model_files = []

    for root, _, files in os.walk(models_dir):
        for file in files:
            if not file.endswith(".model.lkml"):
                continue

            model_path = os.path.join(root, file)
            model_files.append(model_path)
            try:
                with open(model_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                st.warning(f"Could not read file {model_path}: {e}")
                continue

            model_content_no_comments = strip_lookml_comments(content)
            explores = extract_named_blocks(model_content_no_comments, "explore")
            total_explores += len(explores)

            for exp in explores:
                if "description:" in exp["body"]:
                    explores_with_desc += 1

                primary_view_name_match = re.search(r"\b(?:from|view_name)\s*:\s*([a-zA-Z0-9_]+)\b", exp["body"])
                primary_view_name = primary_view_name_match.group(1) if primary_view_name_match else exp["name"]

                meta = view_metadata.get(primary_view_name, {})
                view_path = meta.get("path")
                desc_coverage = get_view_description_coverage(view_path)

                structure_rows.append(
                    {
                        "Model Path": os.path.relpath(model_path, models_dir),
                        "Explore Name": exp["name"],
                        "Role": "primary",
                        "View Name": primary_view_name,
                        "View Folder": meta.get("folder", "Unknown"),
                        "Description Coverage": desc_coverage,
                    }
                )

                joins = extract_named_blocks(exp["body"], "join")
                total_joins += len(joins)
                for j in joins:
                    if "description:" in j["body"]:
                        joins_with_desc += 1

                    join_view_name_match = re.search(r"\b(?:from|view_name)\s*:\s*([a-zA-Z0-9_]+)\b", j["body"])
                    join_view_name = join_view_name_match.group(1) if join_view_name_match else j["name"]

                    join_meta = view_metadata.get(join_view_name)
                    join_view_path = join_meta.get("path") if join_meta else None
                    join_desc_coverage = get_view_description_coverage(join_view_path)

                    if join_view_path:
                        try:
                            with open(join_view_path, "r", encoding="utf-8") as vf:
                                view_content = vf.read()
                            if not _has_primary_key(view_content):
                                views_without_pk.add(join_view_name)
                        except Exception:
                            views_without_pk.add(join_view_name)
                    elif join_view_name:
                        views_without_pk.add(join_view_name)

                    structure_rows.append(
                        {
                            "Model Path": os.path.relpath(model_path, models_dir),
                            "Explore Name": exp["name"],
                            "Role": "join",
                            "View Name": join_view_name,
                            "View Folder": join_meta.get("folder", "Unknown") if join_meta else "Unknown",
                            "Description Coverage": join_desc_coverage,
                        }
                    )

    if not structure_rows:
        st.info("No explores or joins were found in any model files.")
        return None, {}

    df = pd.DataFrame(structure_rows)
    # Reorder columns to be more logical
    cols = ["Model Path", "Explore Name", "Role", "View Name", "View Folder", "Description Coverage"]
    df = df[cols]

    analysis_summary = {
        "df": df,
        "files_with_multiple_views": files_with_multiple_views,
        "views_without_pk": list(views_without_pk),
        "project_stats": {
            "models": len(model_files),
            "views": len(view_metadata),
            "explores": total_explores,
            "joins": total_joins,
        },
        "description_stats": {
            "explores_with_desc": explores_with_desc,
            "total_explores": total_explores,
            "joins_with_desc": joins_with_desc,
            "total_joins": total_joins,
        },
    }
    return df, analysis_summary


def generate_assessment(summary: dict) -> str:
    """Generates a detailed assessment based on the analysis summary."""
    positives, negatives = [], []
    df = summary["df"]

    # --- Negative Checks ---
    unknown_views = df[df["View Folder"] == "Unknown"]["View Name"].unique()
    if unknown_views.size > 0:
        items = "".join(f"<li><code>{v}</code></li>" for v in unknown_views)
        negatives.append(
            f"**Critical: Missing View Files**<br>"
            f"The model refers to views that could not be found in the `/views` directory. "
            f"This will cause validation errors in Looker.<ul>{items}</ul>"
        )

    if summary["files_with_multiple_views"]:
        items = "".join(f"<li><code>{f}</code></li>" for f in summary["files_with_multiple_views"])
        negatives.append(
            "**Recommendation: One View per File**<br>"
            "Best practice is to define only one view per `.view.lkml` file to improve readability "
            "and reduce merge conflicts. The following files contain multiple view definitions:"
            f"<ul>{items}</ul>"
        )

    if summary["views_without_pk"]:
        items = "".join(f"<li><code>{v}</code></li>" for v in summary["views_without_pk"])
        negatives.append(
            "**Critical: Views Joined Without a Primary Key**<br>"
            "A view should have a primary key to be safely used in a join. "
            "This prevents incorrect fanouts and ensures accurate measures. "
            "The following views are joined without a detectable primary key:"
            f"<ul>{items}</ul>"
        )

    snake_case_pattern = re.compile(r"^[a-z0-9_]+$")
    non_snake_case_views = {
        v for v in df["View Name"].unique() if v and not snake_case_pattern.match(v) and v not in unknown_views
    }
    if non_snake_case_views:
        items = "".join(f"<li><code>{v}</code></li>" for v in non_snake_case_views)
        negatives.append(
            "**Recommendation: View Naming Convention**<br>"
            "Best practice recommends `snake_case` for view names. The following views appear to deviate "
            "from this convention:"
            f"<ul>{items}</ul>"
        )

    # --- Positive Checks ---
    if unknown_views.size == 0:
        positives.append("**Good File Integrity**: All views referenced in models were successfully located in the `/views` directory.")
    if not non_snake_case_views and df["View Name"].unique().size > 0:
        positives.append("**Consistent Naming**: All view names appear to follow the `snake_case` convention, which improves readability.")
    if not summary["views_without_pk"]:
        positives.append("**Correct Join Structure**: All views used in joins appear to have a primary key defined, which is essential for accurate results.")

    # --- Build Final Output ---
    if not negatives:
        output = "### ✅ All Good\n"
        output += "This project adheres to all checked LookML best practices."
        if positives:
            output += "<br><br>**Positive Findings**"
            output += "<ul>" + "".join(f"<li>{p}</li>" for p in positives) + "</ul>"
        return output

    # --- Build Section for Recommendations ---
    output = "### 💡 Recommendations for Improvement\n<ul>"
    output += "".join(f"<li>{n}</li>" for n in negatives)
    output += "</ul>"

    if positives:
        output += "<br>### ✅ Positive Findings\n<ul>" + "".join(f"<li>{p}</li>" for p in positives) + "</ul>"

    return output


# --- Streamlit App UI ---

# --- Sidebar ---
with st.sidebar:
    st.title("LookML Project Analyzer")
    st.markdown(
        "Enter a public GitHub repository URL to analyze its LookML structure, "
        "view dependencies, and check for common best practice violations."
    )

    repo_url = st.text_input(
        "GitHub Repository URL",
        placeholder="https://github.com/looker-open-source/looker-ios-sdk",
    )

    analyze_button = st.button("Analyze Repository", use_container_width=True, type="primary")

# --- Main Page ---
st.header("Analysis Results")

if 'analysis_summary' not in st.session_state:
    st.session_state.analysis_summary = None

if analyze_button:
    if not repo_url or not re.match(r"^https?://github\.com/.+/.+$", repo_url):
        st.error("Invalid GitHub URL. Please use the format: https://github.com/owner/repo-name")
        st.session_state.analysis_summary = None
    else:
        temp_dir = tempfile.mkdtemp()
        try:
            progress_bar = st.progress(0, "Cloning repository...")
            process = subprocess.run(["git", "clone", repo_url, temp_dir], capture_output=True, text=True, check=False)

            if process.returncode != 0:
                st.error("Failed to clone repository. Please check the URL and ensure it's a public repository.")
                st.code(process.stderr)
                st.session_state.analysis_summary = None
            else:
                progress_bar.progress(50, "Analyzing LookML files...")
                
                repo_content = os.listdir(temp_dir)
                repo_base_path = os.path.join(temp_dir, repo_content[0]) if len(repo_content) == 1 and os.path.isdir(os.path.join(temp_dir, repo_content[0])) else temp_dir

                df, summary = analyze_repo(repo_base_path)
                st.session_state.analysis_summary = summary
                progress_bar.progress(100, "Analysis complete!")
                progress_bar.empty()

        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
            st.session_state.analysis_summary = None
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

# --- Display Results ---
summary = st.session_state.analysis_summary

if summary:
    stats = summary.get("project_stats", {})
    df = summary.get("df")

    st.subheader("Project Overview")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Models", stats.get('models', 0))
    col2.metric("Views", stats.get('views', 0))
    col3.metric("Explores", stats.get('explores', 0))
    col4.metric("Joins", stats.get('joins', 0))

    st.subheader("Best Practices Assessment")
    assessment = generate_assessment(summary)
    st.markdown(assessment, unsafe_allow_html=True)
    
    if df is not None and not df.empty:
        with st.expander("Show Detailed Structure Analysis", expanded=False):
            st.dataframe(
                df.style.format({"Description Coverage": "{:.1%}"}),
                use_container_width=True
            )
            
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download Full Analysis as CSV",
                data=csv,
                file_name="lookml_structure_analysis.csv",
                mime="text/csv",
                use_container_width=True
            )
else:
    st.info("Enter a repository URL in the sidebar and click 'Analyze Repository' to begin.")
