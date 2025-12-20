import streamlit as st
import os
import re
import pandas as pd
import tempfile
import shutil
import subprocess
from collections import defaultdict

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

    structure_rows = []
    views_without_pk = set()
    explores_with_desc = 0
    joins_with_desc = 0
    total_explores = 0
    total_joins = 0
    model_files = []

    for root, _, files in os.walk(models_dir):
        for file in files:
            if file.endswith(".model.lkml"):
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
                    structure_rows.append(
                        {
                            "Model Path": os.path.relpath(model_path, models_dir),
                            "Explore Name": exp["name"],
                            "Role": "primary",
                            "View Name": primary_view_name,
                            "Join Name": "",
                            "View Folder": meta.get("folder", "Unknown"),
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

                        if join_meta and join_meta.get("path"):
                            try:
                                with open(join_meta["path"], "r", encoding="utf-8") as vf:
                                    view_content = vf.read()
                                if not _has_primary_key(view_content):
                                    views_without_pk.add(join_view_name)
                            except Exception:
                                views_without_pk.add(join_view_name)  # Also flag if unreadable
                        elif join_view_name:
                            views_without_pk.add(join_view_name)  # Also flag if view file is not found at all

                        structure_rows.append(
                            {
                                "Model Path": os.path.relpath(model_path, models_dir),
                                "Explore Name": exp["name"],
                                "Role": "join",
                                "View Name": join_view_name,
                                "Join Name": j["name"],
                                "View Folder": join_meta.get("folder", "Unknown") if join_meta else "Unknown",
                            }
                        )

    if not structure_rows:
        st.info("No explores or joins were found in any model files.")
        return None, {}

    df = pd.DataFrame(structure_rows)
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
        v for v in df["View Name"].unique() if not snake_case_pattern.match(v) and v not in unknown_views
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
    # If no violations exist, show only "All good" and optional positives. No recommendations section.
    if not negatives:
        output = "### ✅ All good\n"
        output += "No files were found that violate LookML best practices."
        if positives:
            output += "<br><br>**Positive findings**"
            output += "<ul>" + "".join(f"<li>{p}</li>" for p in positives) + "</ul>"
        return output

    # Only reach here if there are actual issues
    stats = summary["project_stats"]
    desc_stats = summary["description_stats"]
    observations = [
        f"**Project Size**: The project consists of **{stats['models']}** model(s), **{stats['views']}** view(s), and **{stats['explores']}** explore(s)."
    ]
    if stats["explores"] > 75 or stats["views"] > 150:
        observations.append("Given the project's size, consider organizing LookML into domain-specific folders if you are not already doing so.")

    try:
        explore_desc_pct = (desc_stats["explores_with_desc"] / desc_stats["total_explores"]) * 100
        observations.append(f"**Documentation Coverage**: **{explore_desc_pct:.0f}%** of explores have a `description` tag. Adding descriptions to all explores improves usability for business users.")
    except ZeroDivisionError:
        pass

    output = "### Observations\n<ul>" + "".join(f"<li>{o}</li>" for o in observations) + "</ul>"
    if positives:
        output += "<br>### ✅ Positive Findings\n<ul>" + "".join(f"<li>{p}</li>" for p in positives) + "</ul>"

    output += "<br>### 💡 Recommendations for Improvement\n<ul>"
    output += "".join(f"<li>{n}</li>" for n in negatives)
    output += "</ul>"

    return output


# --- Streamlit App ---

st.set_page_config(layout="wide")
st.title("🔎 LookML Structure Analyzer")

repo_url = st.text_input("Enter the GitHub repository URL:", placeholder="https://github.com/looker-open-source/looker-ios-sdk")

if st.button("Analyze Repository"):
    if not repo_url or not re.match(r"^https?://github\.com/.+/.+$", repo_url):
        st.error("Invalid GitHub URL. Please use the format https://github.com/owner/repo-name")
    else:
        temp_dir = tempfile.mkdtemp()
        try:
            with st.spinner(f"Cloning repository from {repo_url}..."):
                process = subprocess.run(["git", "clone", repo_url, temp_dir], capture_output=True, text=True)
                if process.returncode != 0:
                    st.error("Failed to clone repository.")
                    st.code(process.stderr)
                else:
                    st.success("Repository cloned! Analyzing files...")
                    repo_content = os.listdir(temp_dir)
                    repo_base_path = temp_dir if len(repo_content) > 1 else os.path.join(temp_dir, repo_content[0])

                    df, summary = analyze_repo(repo_base_path)

                    if df is not None:
                        st.subheader("Best Practices Assessment")
                        with st.spinner("Assessing repository against best practices..."):
                            assessment = generate_assessment(summary)
                            st.markdown(assessment, unsafe_allow_html=True)

                        st.subheader("Repository Structure Analysis")
                        st.dataframe(df)

                        csv = df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            label="Download as CSV",
                            data=csv,
                            file_name="lookml_structure.csv",
                            mime="text/csv",
                        )
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
