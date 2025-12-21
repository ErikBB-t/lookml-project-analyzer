import streamlit as st
import os
import re
import pandas as pd
import tempfile
import shutil
import subprocess
from functools import lru_cache
import json

# --- Streamlit Page Configuration & Styling ---
st.set_page_config(
    page_title="LookML Project Analyzer",
    page_icon="🧩",
    layout="wide",
    initial_sidebar_state="expanded",
)

def apply_styling():
    """Injects custom CSS for a modern, dark theme."""
    st.markdown("""
    <style>
        /* General App Styling */
        .stApp {
            background-color: #0E1117;
        }
        h1, h2, h3, h4, h5, h6 {
            color: #FAFAFA;
        }
        .stMarkdown, .stDataFrame, .stMetric {
            color: #EAECEF;
        }

        /* Sidebar */
        [data-testid="stSidebar"] {
            width: 350px !important;
        }

        /* Buttons */
        .stButton>button {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.2s ease-in-out;
            border: 2px solid #4A90E2;
            background-color: transparent;
            color: #4A90E2;
        }
        .stButton>button:hover {
            border-color: #357ABD;
            background-color: #4A90E2;
            color: white;
        }
        .stButton>button:focus {
            box-shadow: none !important;
            color: white;
        }
        
        /* Assessment Cards */
        .assessment-card {
            border: 1px solid #262730;
            border-radius: 10px;
            padding: 1.2rem;
            margin-bottom: 1rem;
            background-color: #161a25;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .assessment-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 16px rgba(0,0,0,0.3);
        }
        .assessment-title {
            font-size: 1.15em;
            font-weight: 600;
            margin-bottom: 0.5rem;
        }
        .assessment-details ul {
            padding-left: 20px;
            margin-top: 5px;
            font-size: 0.95em;
        }
        .assessment-details li {
            margin-bottom: 0.3rem;
        }
        
        /* Card Severity Borders */
        .critical { border-left: 5px solid #d9534f; }
        .recommendation { border-left: 5px solid #f0ad4e; }
        .positive { border-left: 5px solid #5cb85c; }
    </style>
    """, unsafe_allow_html=True)

apply_styling()


# --- Core Parsing and Analysis Functions ---

def map_views_to_metadata(views_dir: str) -> tuple[dict, list]:
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
                        files_with_multiple_views.append(os.path.relpath(file_path, views_dir))
                    if not found_views:
                        found_views.append(file.replace(".view.lkml", ""))
                    relative_dir = os.path.relpath(root, views_dir)
                    folder = relative_dir.split(os.sep)[0] if relative_dir != "." else "(root)"
                    for view_name in found_views:
                        view_metadata_map[view_name] = {"folder": folder, "path": file_path}
                except Exception:
                    continue
    return view_metadata_map, files_with_multiple_views

def strip_lookml_comments(text: str) -> str:
    return re.sub(r"#.*", "", text)

def find_matching_brace(text: str, open_brace_index: int) -> int:
    depth = 1
    for i in range(open_brace_index + 1, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
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
    if not view_path or not os.path.exists(view_path): return None
    try:
        with open(view_path, "r", encoding="utf-8") as f: content = f.read()
    except Exception: return None
    uncommented = strip_lookml_comments(content)
    dims = extract_named_blocks(uncommented, "dimension")
    measures = extract_named_blocks(uncommented, "measure")
    total = len(dims) + len(measures)
    if total == 0: return 1.0
    described = sum(1 for f in dims + measures if "description:" in f["body"])
    return described / total

def _has_primary_key(view_content: str) -> bool:
    dimensions = extract_named_blocks(strip_lookml_comments(view_content), "dimension")
    return any("primary_key: yes" in dim["body"] for dim in dimensions)

def get_view_extensions(views_dir: str) -> dict:
    extensions = {}
    if not os.path.isdir(views_dir): return extensions
    for root, _, files in os.walk(views_dir):
        for file in files:
            if file.endswith(".view.lkml"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f: content = f.read()
                    uncommented = strip_lookml_comments(content)
                    for block in extract_named_blocks(uncommented, "view"):
                        match = re.search(r"\bextends\s*:\s*\[([^\]]*)\]", block["body"])
                        extensions[block["name"]] = " ".join([v.strip() for v in match.group(1).split(",") if v.strip()]) if match else ""
                except Exception:
                    continue
    return extensions

def analyze_repo(repo_path: str):
    views_dir, models_dir = os.path.join(repo_path, "views"), os.path.join(repo_path, "models")
    if not os.path.isdir(models_dir):
        st.error("The 'models' directory was not found. Please ensure this is a standard LookML project.")
        return None, {}

    view_metadata, multi_view_files = map_views_to_metadata(views_dir)
    view_extensions = get_view_extensions(views_dir)
    get_view_description_coverage.cache_clear()

    rows, views_no_pk, joins_no_rel, joins_sql_func = [], set(), set(), set()
    explores_total, explores_desc = 0, 0
    joins_total, joins_desc = 0, 0
    model_files = [os.path.join(r, f) for r, _, f_list in os.walk(models_dir) for f in f_list if f.endswith(".model.lkml")]

    for model_path in model_files:
        try:
            with open(model_path, "r", encoding="utf-8") as f: content = f.read()
        except Exception as e:
            st.warning(f"Could not read file {model_path}: {e}")
            continue

        no_comments = strip_lookml_comments(content)
        explores = extract_named_blocks(no_comments, "explore")
        explores_total += len(explores)

        for exp in explores:
            if "description:" in exp["body"]:
                explores_desc += 1
            
            primary_view_name_match = re.search(r"\b(?:from|view_name)\s*:\s*([a-zA-Z0-9_]+)\b", exp["body"])
            primary_view_name = primary_view_name_match.group(1) if primary_view_name_match else exp["name"]

            meta = view_metadata.get(primary_view_name, {})
            rows.append({
                "Model Path": os.path.relpath(model_path, models_dir), "Explore Name": exp["name"], "Role": "primary",
                "View Name": primary_view_name, "View Folder": meta.get("folder", "Unknown"),
                "Description Coverage": get_view_description_coverage(meta.get("path")),
                "Extends On": view_extensions.get(primary_view_name, ""),
            })

            joins = extract_named_blocks(exp["body"], "join")
            joins_total += len(joins)
            for j in joins:
                if "description:" in j["body"]:
                    joins_desc += 1
                if "relationship:" not in j["body"]:
                    joins_no_rel.add(f"`{j['name']}` in explore `{exp['name']}`")
                
                sql_on = re.search(r"sql_on:\s*(.+?)\s*;;", j["body"], re.DOTALL)
                if sql_on and re.search(r"[a-zA-Z_][a-zA-Z0-9_]*\s*\(", sql_on.group(1)):
                  joins_sql_func.add(f"`{j['name']}` in explore `{exp['name']}`")


                join_view_name_match = re.search(r"\b(?:from|view_name)\s*:\s*([a-zA-Z0-9_]+)\b", j["body"])
                join_view_name = join_view_name_match.group(1) if join_view_name_match else j["name"]
                join_meta = view_metadata.get(join_view_name, {})
                
                if path := join_meta.get("path"):
                    try:
                        with open(path, "r", encoding="utf-8") as vf:
                            if not _has_primary_key(vf.read()): views_no_pk.add(join_view_name)
                    except Exception: views_no_pk.add(join_view_name)
                elif join_view_name:
                    views_no_pk.add(join_view_name)
                
                rows.append({
                    "Model Path": os.path.relpath(model_path, models_dir), "Explore Name": exp["name"], "Role": "join",
                    "View Name": join_view_name, "View Folder": join_meta.get("folder", "Unknown"),
                    "Description Coverage": get_view_description_coverage(join_meta.get("path")),
                    "Extends On": view_extensions.get(join_view_name, ""),
                })
    
    if not rows: return None, {}
    df = pd.DataFrame(rows)[["Model Path", "Explore Name", "Role", "View Name", "View Folder", "Description Coverage", "Extends On"]]
    return df, {
        "df": df, "files_with_multiple_views": multi_view_files, "views_without_pk": list(views_no_pk),
        "joins_without_relationship": list(joins_no_rel), "joins_with_sql_on_functions": list(joins_sql_func),
        "project_stats": {"models": len(model_files), "views": len(view_metadata), "explores": explores_total, "joins": joins_total},
        "description_stats": {"explores_with_desc": explores_desc, "total_explores": explores_total, "joins_with_desc": joins_desc, "total_joins": joins_total},
    }

def generate_assessment(summary: dict) -> list:
    assessments, df = [], summary["df"]
    
    # --- Analysis ---
    unknown_views = df[df["View Folder"] == "Unknown"]["View Name"].unique()
    non_snake_views = {v for v in df["View Name"].unique() if v and not re.match(r"^[a-z0-9_]+$", v) and v not in unknown_views}

    # --- Negative Findings ---
    if unknown_views.size > 0:
        assessments.append({"severity": "Critical", "title": "Missing View Files", "details": f"The model refers to views that could not be found, which will cause validation errors:<ul>{''.join(f'<li><code>{v}</code></li>' for v in unknown_views)}</ul>"})
    if summary["views_without_pk"]:
        assessments.append({"severity": "Critical", "title": "Views Joined Without a Primary Key", "details": f"Joins require a primary key to prevent fanouts and ensure accurate measures. The following views are used in joins but lack a defined primary key:<ul>{''.join(f'<li><code>{v}</code></li>' for v in summary['views_without_pk'])}</ul>"})
    if summary["joins_with_sql_on_functions"]:
        assessments.append({"severity": "Critical", "title": "SQL Functions in Join Conditions", "details": f"Using functions in `sql_on` can severely degrade query performance by preventing the database from using indexes. This was found in the following joins:<ul>{''.join(f'<li>{j}</li>' for j in summary['joins_with_sql_on_functions'])}</ul>"})
    if summary["joins_without_relationship"]:
        assessments.append({"severity": "Recommendation", "title": "Joins Missing Explicit Relationship", "details": f"Always define the `relationship` parameter in joins. Relying on the default (many_to_one) can hide modeling errors and lead to incorrect results if the relationship is different. Missing in:<ul>{''.join(f'<li>{j}</li>' for j in summary['joins_without_relationship'])}</ul>"})
    if summary["files_with_multiple_views"]:
        assessments.append({"severity": "Recommendation", "title": "Multiple Views Defined in a Single File", "details": f"Best practice is one view per `.view.lkml` file for readability and easier maintenance. Multiple views were found in:<ul>{''.join(f'<li><code>{f}</code></li>' for f in summary['files_with_multiple_views'])}</ul>"})
    
    if non_snake_views:
        assessments.append({"severity": "Recommendation", "title": "View Naming Convention", "details": f"Best practice recommends `snake_case` for view names to improve readability. The following views appear to deviate:<ul>{''.join(f'<li><code>{v}</code></li>' for v in non_snake_views)}</ul>"})

    # --- Positive Findings ---
    if unknown_views.size == 0: 
        assessments.append({"severity": "Positive", "title": "Good File Integrity", "details": "All views referenced in models were successfully located."})
    if not summary["views_without_pk"]:
        assessments.append({"severity": "Positive", "title": "Correct Join Structure", "details": "All views used in joins appear to have a primary key defined."})
    
    return sorted(assessments, key=lambda x: ("Critical", "Recommendation", "Positive").index(x['severity']))

def generate_graph_data(df: pd.DataFrame) -> dict:
    """
    Converts the analysis DataFrame into a vis.js compatible graph format.
    - Uses unique IDs to prevent node collision.
    - Assigns mass to nodes and length to edges to create a physics-based
      'galaxy' or 'solar system' layout.
    """
    nodes, edges = [], []
    node_ids = set()

    # Define mass and length for the physics simulation
    MASS_MODEL = 10
    MASS_EXPLORE = 4
    MASS_VIEW = 1
    LENGTH_MODEL_TO_EXPLORE = 450
    LENGTH_EXPLORE_TO_VIEW = 200

    for _, row in df.iterrows():
        model_path = row["Model Path"]
        explore_name = row["Explore Name"]
        view_name = row["View Name"]

        model_node_id = f"model_{model_path}"
        explore_node_id = f"explore_{model_path}_{explore_name}"
        view_node_id = f"view_{view_name}"

        # Add model node (the "sun")
        if model_node_id not in node_ids:
            nodes.append({
                "id": model_node_id, "label": model_path, "group": "model",
                "title": f"Model File: {model_path}", "mass": MASS_MODEL
            })
            node_ids.add(model_node_id)
            
        # Add explore node (the "planet")
        if explore_node_id not in node_ids:
            nodes.append({
                "id": explore_node_id, "label": explore_name, "group": "explore",
                "title": f"Explore: {explore_name}\nModel: {model_path}", "mass": MASS_EXPLORE
            })
            node_ids.add(explore_node_id)

        # Add view node (the "moon")
        if view_node_id not in node_ids:
            nodes.append({
                "id": view_node_id, "label": view_name, "group": "view",
                "title": f"View: {view_name}", "mass": MASS_VIEW
            })
            node_ids.add(view_node_id)
            
        # Add edges with specific lengths
        edges.append({
            "from": model_node_id, "to": explore_node_id, "length": LENGTH_MODEL_TO_EXPLORE,
            "title": f"{model_path} -> {explore_name}"
        })
        edges.append({
            "from": explore_node_id, "to": view_node_id, "label": row["Role"], "length": LENGTH_EXPLORE_TO_VIEW,
            "title": f"{explore_name} -> {view_name} ({row['Role']})"
        })

    return {"nodes": nodes, "edges": edges}


# --- Streamlit App UI ---

with st.sidebar:
    st.title("LookML Project Analyzer")
    st.markdown("Enter a public GitHub repository URL to analyze its LookML structure and check for best practice violations.")
    repo_url = st.text_input("GitHub Repository URL", placeholder="https://github.com/owner/repo")
    
    col1, col2 = st.columns(2)
    with col1:
        analyze_button = st.button("Analyze Project", use_container_width=True, type="primary")
    with col2:
        clear_button = st.button("Reset", use_container_width=True)

if clear_button:
    st.session_state.analysis_summary = None
    st.rerun()

st.header("Analysis Results")

if 'analysis_summary' not in st.session_state:
    st.session_state.analysis_summary = None

if analyze_button:
    if not repo_url or not re.match(r"^https?://github\.com/.+/.+$", repo_url):
        st.error("Invalid GitHub URL. Please use the format: https://github.com/owner/repo")
        st.session_state.analysis_summary = None
    else:
        with st.spinner(f"Cloning {repo_url}..."):
            temp_dir = tempfile.mkdtemp()
            try:
                subprocess.run(["git", "clone", repo_url, temp_dir], capture_output=True, text=True, check=True)
                
                with st.spinner("Analyzing LookML files..."):
                    df, summary = analyze_repo(temp_dir)
                    st.session_state.analysis_summary = summary
                st.success("Analysis complete!")

            except subprocess.CalledProcessError as e:
                st.error(f"Failed to clone repository. Check the URL and ensure it is a public repo.\n\nGit Error: {e.stderr}")
                st.session_state.analysis_summary = None
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")
                st.session_state.analysis_summary = None
            finally:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)

summary = st.session_state.analysis_summary

if summary:
    stats, df = summary.get("project_stats", {}), summary.get("df")

    st.subheader("Project Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Models", stats.get('models', 0))
    c2.metric("Views", stats.get('views', 0))
    c3.metric("Explores", stats.get('explores', 0))
    c4.metric("Joins", stats.get('joins', 0))

    st.subheader("Best Practices Assessment")
    assessments = generate_assessment(summary)
    if not any(a['severity'] in ("Critical", "Recommendation") for a in assessments):
        st.success("Excellent! No critical issues or major recommendations found.")
    
    for a in assessments:
        st.markdown(f"""
        <div class="assessment-card {a['severity'].lower()}">
            <div class="assessment-title">{a['title']}</div>
            <div class="assessment-details">{a['details']}</div>
        </div>
        """, unsafe_allow_html=True)
    
    if df is not None and not df.empty:
        st.subheader("Interactive Project Graph")
        try:
            with open("templates/graph.html") as f:
                graph_html = f.read()
            graph_data = generate_graph_data(df)
            graph_html = graph_html.replace("%%graph_data%%", json.dumps(graph_data))
            st.components.v1.html(graph_html, height=620)
        except Exception as e:
            st.error(f"Could not generate interactive graph: {e}")

        with st.expander("Show Detailed Structure Analysis", expanded=False):
            st.dataframe(df.style.format({"Description Coverage": "{:.1%}"}), use_container_width=True)
            st.download_button(
                label="Download Full Analysis as CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="lookml_structure_analysis.csv",
                mime="text/csv",
                use_container_width=True,
            )
else:
    st.info("Enter a repository URL in the sidebar and click 'Analyze Project' to begin.")
