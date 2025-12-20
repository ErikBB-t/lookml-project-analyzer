# 🔎 LookML Structure Analyzer

En enkel web-applikasjon for å analysere strukturen i et Looker (LookML) prosjekt. Applikasjonen tar en URL til et GitHub-repository som input, analyserer alle `.model.lkml`-filer for å finne "explores" og "joins", og kartlegger dem mot de underliggende "views".

Dette gir en oversikt over hvilke views som er i bruk, hvor de brukes, og hvilken mappe de tilhører.

## Funksjoner

-   **Web-basert UI:** Et enkelt grensesnitt bygget med Streamlit.
-   **Analyser fra GitHub:** Lim inn en link til et hvilket som helst offentlig LookML-repository på GitHub.
-   **Interaktiv Tabell:** Resultatene vises i en oversiktlig og søkbar tabell.
-   **Eksporter til CSV:** Last ned analyseresultatene som en CSV-fil for videre bruk.
-   **Ingen lokal LookML nødvendig:** Hele analysen kjøres "on-the-fly" ved å klone repoet midlertidig.

## Installasjon og Oppsett

Applikasjonen krever Python 3. For å unngå konflikter med system-pakker, anbefales det sterkt å bruke et virtuelt miljø.

**1. Klon eller last ned repoet:**

Hvis du har `git` installert:
```bash
git clone https://github.com/din-bruker/LookML-structure.git
cd LookML-structure
```
Ellers kan du laste ned filene (`app.py`, `list_used_views.py`, `requirements.txt`) og plassere dem i samme mappe.

**2. Opprett et virtuelt miljø:**

Naviger til prosjektmappen i terminalen og kjør:
```bash
python3 -m venv venv
```
Dette lager en ny mappe `venv` som vil inneholde alle prosjektets avhengigheter.

**3. Installer avhengigheter:**

Installer de nødvendige Python-bibliotekene inn i det virtuelle miljøet:
```bash
./venv/bin/pip install -r requirements.txt
```
Dette installerer Streamlit, Pandas og andre nødvendige pakker.

## Hvordan bruke appen

Når installasjonen er fullført, kan du starte applikasjonen.

**1. Start Streamlit-serveren:**

Pass på at du er i prosjektmappen og kjør:
```bash
./venv/bin/streamlit run app.py
```

**2. Åpne i nettleseren:**

Etter å ha kjørt kommandoen over, vil en ny fane automatisk åpnes i nettleseren din. Hvis ikke, kan du navigere til `http://localhost:8501`.

**3. Analyser et repository:**

-   Finn URL-en til et LookML-prosjekt på GitHub (f.eks. `https://github.com/looker-open-source/looker-ios-sdk`).
-   Lim inn URL-en i tekstfeltet i applikasjonen.
-   Klikk på "Analyser repo".
-   Appen vil klone repoet, kjøre analysen og vise resultatene.

## Hvordan det fungerer

Applikasjonen utfører følgende steg:
1.  **Input:** Tar imot en GitHub URL fra brukeren.
2.  **Klone:** Bruker `git` til å laste ned en midlertidig kopi av repoet.
3.  **Kartlegge Views:** Skanner `views`-mappen for å lage en oversikt over alle `.view.lkml`-filer og deres plassering.
4.  **Parse Modeller:** Leser hver `.model.lkml`-fil i `models`-mappen. Den fjerner kommentarer og bruker regulære uttrykk for å identifisere `explore`- og `join`-blokker.
5.  **Identifisere koblinger:** For hver explore og join finner den det faktiske view-navnet som brukes (håndterer `from:` og `view_name:`).
6.  **Presentere data:** Samler all informasjonen i en Pandas DataFrame som vises i en interaktiv tabell i Streamlit.
7.  **Opprydding:** Sletter den midlertidige mappen med det klonede repoet.
