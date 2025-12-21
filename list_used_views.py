
import os
import re
import csv
import sys  # for sys.stderr


def get_view_description_stats(views_dir: str) -> dict:
    """
    Scans all .view.lkml files in a directory, and for each view,
    calculates the percentage of fields that have a description.
    """
    stats = {}
    if not os.path.isdir(views_dir):
        return stats

    for root, _, files in os.walk(views_dir):
        for file in files:
            if not file.endswith(".view.lkml"):
                continue

            view_name = file.replace(".view.lkml", "")
            file_path = os.path.join(root, file)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                print(f"Error reading view file {file_path}: {e}", file=sys.stderr)
                continue

            content = strip_lookml_comments(content)

            # Find all view blocks in the file
            view_blocks = extract_named_blocks(content, "view")

            if not view_blocks:
                continue

            view_body = view_blocks[0]['body']

            total_fields = 0
            fields_with_description = 0

            # Find all dimensions, dimension_groups, and measures
            field_types = ["dimension", "dimension_group", "measure"]
            for field_type in field_types:
                fields = extract_named_blocks(view_body, field_type)
                for field in fields:
                    total_fields += 1
                    # Check for `description:` in the body of the field
                    if re.search(r"\bdescription\s*:", field["body"]):
                        fields_with_description += 1

            percentage = (fields_with_description / total_fields * 100) if total_fields > 0 else 0

            stats[view_name] = {
                "total_fields": total_fields,
                "fields_with_description": fields_with_description,
                "description_percentage": round(percentage, 2)
            }

    return stats


def get_view_extensions(views_dir: str) -> dict:
    """
    Scans all .view.lkml files in a directory and for each view,
    finds the views it extends.
    Returns a dict mapping view name to a space-separated list of extended views.
    """
    extensions = {}
    if not os.path.isdir(views_dir):
        return extensions

    for root, _, files in os.walk(views_dir):
        for file in files:
            if not file.endswith(".view.lkml"):
                continue

            file_path = os.path.join(root, file)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                print(f"Error reading view file {file_path}: {e}", file=sys.stderr)
                continue

            content = strip_lookml_comments(content)
            view_blocks = extract_named_blocks(content, "view")

            for view_block in view_blocks:
                view_name = view_block["name"]
                view_body = view_block["body"]

                match = re.search(r"\bextends\s*:\s*\[([^\]]*)\]", view_body)
                if match:
                    extended_list = [v.strip() for v in match.group(1).split(",") if v.strip()]
                    extensions[view_name] = " ".join(extended_list)
                else:
                    if view_name not in extensions:
                        extensions[view_name] = ""
    return extensions


def map_views_to_folders(views_dir: str) -> dict:
    """
    Scans the views directory to create a map of view names to their parent folder.
    The parent folder is the directory directly under the main 'views' directory.
    """
    view_to_folder_map = {}
    if not os.path.isdir(views_dir):
        return view_to_folder_map

    for root, _, files in os.walk(views_dir):
        for file in files:
            if file.endswith(".view.lkml"):
                view_name = file.replace(".view.lkml", "")

                relative_dir = os.path.relpath(root, views_dir)
                path_parts = relative_dir.split(os.sep)

                if path_parts and path_parts[0] not in [".", ""]:
                    folder = path_parts[0]
                else:
                    folder = "(root)"

                view_to_folder_map[view_name] = folder

    return view_to_folder_map


def strip_lookml_comments(text: str) -> str:
    """
    Removes LookML line comments starting with '#'.
    This is intentionally simple: it may remove hashes inside strings,
    but in practice it's usually fine for LookML parsing.
    """
    return re.sub(r"#.*", "", text)


def find_matching_brace(text: str, open_brace_index: int) -> int:
    """
    Given index of '{' in text, returns index of matching '}'.
    Returns -1 if not found.
    """
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
    """
    Extract blocks like:
      <keyword>: <name> { ... }
    Returns list of dicts: { "name": str, "body": str }
    """
    blocks = []
    pattern = re.compile(rf"\b{re.escape(keyword)}\s*:\s*([a-zA-Z0-9_]+)\s*\{{")
    for m in pattern.finditer(text):
        name = m.group(1)
        open_brace_index = m.end() - 1  # points at '{'
        close_brace_index = find_matching_brace(text, open_brace_index)
        if close_brace_index == -1:
            continue
        body = text[open_brace_index + 1 : close_brace_index]
        blocks.append({"name": name, "body": body})
    return blocks


def parse_view_override(block_body: str) -> str | None:
    """
    Tries to find from: <view> or view_name: <view> inside a block body.
    Returns the view name if found, else None.
    """
    m = re.search(r"\b(?:from|view_name)\s*:\s*([a-zA-Z0-9_]+)\b", block_body)
    return m.group(1) if m else None


def parse_explore_usage(model_content: str) -> list:
    """
    Parses a model file content and returns a list of rows:
      {
        "explore": <explore_name>,
        "role": "primary" | "join",
        "view_name": <actual_view_name>,
        "join_name": <join_name or ''>
      }
    """
    rows = []

    model_content = strip_lookml_comments(model_content)

    explores = extract_named_blocks(model_content, "explore")
    for exp in explores:
        explore_name = exp["name"]
        explore_body = exp["body"]

        # Primary view: default is explore name, but can be overridden via from/view_name inside explore block.
        primary_view = parse_view_override(explore_body) or explore_name
        rows.append(
            {
                "explore": explore_name,
                "role": "primary",
                "view_name": primary_view,
                "join_name": "",
            }
        )

        # Joins inside explore block
        joins = extract_named_blocks(explore_body, "join")
        for j in joins:
            join_name = j["name"]
            join_body = j["body"]

            # Join view: default is join name, but can be overridden via from/view_name inside join block.
            join_view = parse_view_override(join_body) or join_name

            rows.append(
                {
                    "explore": explore_name,
                    "role": "join",
                    "view_name": join_view,
                    "join_name": join_name,
                }
            )

    return rows


def main():
    views_dir = "views"
    models_dir = "models"
    output_filename = "lookml_structure.csv"

    print(f"Scanning '{views_dir}' to map views to folders...", file=sys.stderr)
    view_to_folder = map_views_to_folders(views_dir)
    print("...done.\n", file=sys.stderr)

    print(f"Analyzing descriptions in '{views_dir}'...", file=sys.stderr)
    description_stats = get_view_description_stats(views_dir)
    print("...done.\n", file=sys.stderr)

    print(f"Scanning '{views_dir}' for view extensions...", file=sys.stderr)
    view_extensions = get_view_extensions(views_dir)
    print("...done.\n", file=sys.stderr)


    if not os.path.isdir(models_dir):
        print(f"Error: Directory '{models_dir}' not found in the current location.", file=sys.stderr)
        return

    csv_rows = []
    csv_rows.append([
        "Model Path", "Explore Name", "Role", "View Name", "Join Name", "View Folder",
        "Fields with Description", "Total Fields", "Description Coverage (%)", "Extends On"
    ])

    models_found = 0
    explores_found = 0

    for root, _, files in os.walk(models_dir):
        for file in files:
            if not file.endswith(".model.lkml"):
                continue

            model_path = os.path.join(root, file)
            try:
                with open(model_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                print(f"Error reading file {model_path}: {e}", file=sys.stderr)
                continue

            usage_rows = parse_explore_usage(content)
            if not usage_rows:
                continue

            models_found += 1
            explores_found += len({r["explore"] for r in usage_rows})

            for r in usage_rows:
                view_name = r["view_name"]
                folder = view_to_folder.get(view_name, "Ukjent")
                extends_on = view_extensions.get(view_name, "")

                stats = description_stats.get(view_name, {})
                fields_with_desc = stats.get("fields_with_description", "N/A")
                total_fields = stats.get("total_fields", "N/A")
                desc_percentage = stats.get("description_percentage", "N/A")

                csv_rows.append(
                    [
                        model_path,
                        r["explore"],
                        r["role"],
                        view_name,
                        r["join_name"],
                        folder,
                        fields_with_desc,
                        total_fields,
                        desc_percentage,
                        extends_on,
                    ]
                )

    if len(csv_rows) == 1:
        print(f"No explores/joins found in any models under '{models_dir}'.", file=sys.stderr)
        return

    try:
        with open(output_filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(csv_rows)

        print(f"CSV report generated successfully: {output_filename}", file=sys.stderr)
        print(f"Models parsed: {models_found}", file=sys.stderr)
        print(f"Explores found: {explores_found}", file=sys.stderr)
    except IOError as e:
        print(f"Error writing to file {output_filename}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()