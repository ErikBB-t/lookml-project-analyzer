# LookML Project Analyzer

A simple web application to analyze the structure of a Looker (LookML) project. The application takes a URL to a GitHub repository as input, analyzes all `.model.lkml` files to find "explores" and "joins", and maps them to the underlying "views".

This provides an overview of which views are in use, where they are used, and which folder they belong to.

## Features

-   **Web-based UI:** A Streamlit-based interface for exploring and understanding LookML project structure.
-   **Analyze from GitHub:** Analyze any public LookML repository directly from a GitHub URL, without running Looker or cloning locally.
-   **Dependency and usage mapping:** Maps explores and joins to their underlying views, showing where views are used, from which models, and across which domains. Supports `from:` and `view_name:`.
-   **Project structure and ownership visibility:** Connects views to their folder structure to make domain boundaries and reuse across areas explicit.
-   **Documentation and best practice feedback:** Measures field description coverage and provides basic feedback compared to common LookML best practices.
-   **Interactive graph visualization:** Explore view and explore dependencies through an interactive node-based graph.
-   **Export to CSV:** Export the full analysis for refactoring, audits, governance, or further processing.
-   **No local LookML required:** Runs entirely offline by temporarily cloning the repository for analysis.



## Installation and Setup

The application requires Python 3. To avoid conflicts with system packages, it is strongly recommended to use a virtual environment.

**1. Clone or download the repository:**

If you have `git` installed:
```bash
git clone https://github.com/your-username/LookML-structure.git
cd LookML-structure
```
Otherwise, you can download the files (`app.py`, `list_used_views.py`, `requirements.txt`) and place them in the same folder.

**2. Create a virtual environment:**

Navigate to the project folder in your terminal and run:
```bash
python3 -m venv venv
```
This creates a new folder `venv` that will contain all the project's dependencies.

**3. Install dependencies:**

Install the required Python libraries into the virtual environment:
```bash
./venv/bin/pip install -r requirements.txt
```
This installs Streamlit, Pandas, and other necessary packages.

## How to use the app

Once the installation is complete, you can start the application.

**1. Start the Streamlit server:**

Make sure you are in the project folder and run:
```bash
./venv/bin/streamlit run app.py
```

**2. Open in your browser:**

After running the command above, a new tab will automatically open in your browser. If not, you can navigate to `http://localhost:8501`.

**3. Analyze a repository:**

-   Find the URL of a LookML project on GitHub (e.g., `https://github.com/looker-open-source/looker-ios-sdk`).
-   Paste the URL into the text field in the application.
-   Click "Analyze repo".
-   The app will clone the repository, run the analysis, and display the results.

## How it works

The application performs the following steps:
1.  **Input:** Accepts a GitHub URL from the user.
2.  **Clone:** Uses `git` to download a temporary copy of the repository.
3.  **Map Views:** Scans the `views` folder to create an overview of all `.view.lkml` files and their locations.
4.  **Parse Models:** Reads each `.model.lkml` file in the `models` folder. It removes comments and uses regular expressions to identify `explore` and `join` blocks.
5.  **Identify connections:** For each explore and join, it finds the actual view name used (handles `from:` and `view_name:`).
6.  **Present data:** Gathers all the information into a Pandas DataFrame which is displayed in an interactive table in Streamlit.
7.  **Cleanup:** Deletes the temporary folder with the cloned repository.