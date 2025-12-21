# LookML Project Analyzer

A simple web application to analyze the structure of a Looker (LookML) project. The application takes a URL to a GitHub repository as input, analyzes all `.model.lkml` files to find "explores" and "joins", and maps them to the underlying "views".

This provides an overview of which views are in use, where they are used, and which folder they belong to.

## Features

-   **Web-based UI:** A simple interface built with Streamlit for quickly exploring LookML project structure.
-   **Analyze from GitHub:** Paste a link to any public LookML repository on GitHub and analyze it without cloning or running Looker locally.
-   **Explore and join mapping:** Analyzes `.model.lkml` files to identify explores and joins and resolves them to the actual underlying views, including support for `from:` and `view_name:`.
-   **View usage overview:** Shows which views are in use, where they are used, and which explores and model files depend on them.
-   **Project structure mapping:** Maps each view to its folder within the `views` directory to make ownership and domain boundaries visible.
-   **Documentation coverage analysis:** Calculates the percentage of fields in each view that have descriptions to help assess documentation quality.
-   **Interactive Table:** The results are displayed in a clear and searchable table.
-   **Export to CSV:** Download the analysis results as a CSV file for further use in refactoring, audits, or governance work.
-   **No local LookML required:** The entire analysis is run on-the-fly by temporarily cloning the repository.


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