# Teknisk Dokumentasjon - LookML Structure Analyzer

Denne filen gir en detaljert teknisk oversikt over hvordan `app.py` fungerer internt for å analysere LookML-prosjekter.

## Oversikt

Hovedmålet med skriptet er å dekonstruere LookML-modeller for å skape en eksplisitt kobling mellom "explores", "joins" og de underliggende "views". Dette er informasjon som ikke er lett tilgjengelig i Looker UI, men som er kritisk for å forstå avhengigheter, rydde i kode og analysere prosjektstruktur.

Analysen er skreddersydd for standard LookML-syntaks og prosjektstruktur (`views`- og `models`-mapper).

## Filstruktur

-   `app.py`: Hovedfilen som inneholder all logikk for Streamlit-grensesnittet og LookML-parseren.
-   `list_used_views.py`: Det opprinnelige frittstående skriptet. Funksjonaliteten herfra er nå integrert direkte i `app.py`.
-   `requirements.txt`: Definerer Python-avhengighetene (Streamlit og Pandas).
-   `README.md`: Generell brukerveiledning.
-   `DOCUMENTATION.md`: Denne filen.

## Kjernelogikk: Parsing-prosess

Parsing-logikken er en serie med funksjoner som jobber sammen for å lese og tolke LookML-kode. Siden LookML er et proprietært format uten en standardisert parser (som f.eks. en JSON-parser), er logikken basert på en kombinasjon av filsystem-operasjoner og regulære uttrykk.

### 1. `map_views_to_folders(views_dir)`

-   **Formål:** Før vi kan analysere modellene, må vi vite hvor alle tilgjengelige "views" befinner seg. Denne funksjonen lager en mapping mellom et view-navn og mappen det ligger i.
-   **Prosess:**
    1.  Tar inn stien til `views`-mappen i et klonet repo.
    2.  Går rekursivt gjennom alle undermapper og filer.
    3.  For hver fil som slutter på `.view.lkml`, trekkes view-navnet ut fra filnavnet.
    4.  Mappenavnet rett under `views` blir identifisert som "View Folder".
    5.  Returnerer en dictionary, f.eks. `{ "orders": "core", "users": "core", "products": "ecommerce" }`.

### 2. Tekst-prosessering

LookML-filer leses som ren tekst. Før de kan analyseres, må de ryddes.

-   **`strip_lookml_comments(text)`**: Bruker et enkelt regulært uttrykk (`#.*`) for å fjerne alle kommentarer. Dette forenkler den videre parsing-prosessen.

### 3. Blokk-analyse

LookML er strukturert i blokker med krøllparenteser (`{}`). Koden må kunne identifisere disse for å isolere `explore`- og `join`-definisjoner.

-   **`find_matching_brace(text, open_brace_index)`**: En hjelpefunksjon som finner den korresponderende lukkeparentesen `}` for en gitt åpningsparentes `{`. Den holder styr på dybden for å håndtere nøstede blokker korrekt.
-   **`extract_named_blocks(text, keyword)`**:
    -   **Formål:** Dette er en nøkkelfunksjon som finner alle navngitte blokker av en bestemt type (f.eks. `explore` eller `join`).
    -   **Prosess:**
        1.  Bruker et regulært uttrykk for å finne mønsteret `<keyword>: <name> {`.
        2.  Når den finner et treff, lagrer den navnet (f.eks. `explore_name`).
        3.  Den kaller `find_matching_brace` for å finne slutten på blokken.
        4.  Hele innholdet mellom `{` og `}` blir trukket ut som "body".
        5.  Returnerer en liste med dictionaries, hver med `name` og `body`.

### 4. `parse_explore_usage(model_content)`

-   **Formål:** Dette er orkestrerings-funksjonen for å analysere innholdet i én enkelt modellfil.
-   **Prosess:**
    1.  Kjører `strip_lookml_comments` på filinnholdet.
    2.  Kaller `extract_named_blocks` med `keyword="explore"` for å få en liste over alle explores i filen.
    3.  For hver `explore`:
        a.  **Primært View:** Først antas det at view-navnet er det samme som explore-navnet. Deretter sjekkes det for en `from:` eller `view_name:` parameter inne i explore-blokken ved hjelp av `parse_view_override`. Dette gir det faktiske view-navnet.
        b.  Det legges til en rad for det primære view-et.
        c.  **Joins:** Deretter kalles `extract_named_blocks` på nytt, denne gangen på `explore`-blokkens innhold med `keyword="join"`.
        d.  For hver `join` gjentas samme logikk som i (a) for å finne det faktiske view-navnet for join-en.
        e.  Det legges til en rad for hver join.
    4.  Returnerer en liste med rader, der hver rad er en dictionary som representerer en view-bruk (enten som primær-view eller join-view).

### 5. `analyze_repo(repo_path)` (Streamlit-integrasjon)

-   **Formål:** Binder alt sammen og kjører hele analysen på et klonet repository.
-   **Prosess:**
    1.  Identifiserer `views`- og `models`-mappene basert på repo-stien.
    2.  Kaller `map_views_to_folders` for å bygge view-mappe-oversikten.
    3.  Itererer gjennom alle `.model.lkml`-filer.
    4.  For hver fil kalles `parse_explore_usage`.
    5.  Resultatene fra `parse_explore_usage` kombineres med informasjonen fra `map_views_to_folders` for å lage komplette rader.
    6.  Alle radene samles og konverteres til en Pandas DataFrame, som returneres til Streamlit-appen for visning.

## Håndtering av GitHub Repo

-   **Midlertidig mappe:** Appen bruker Pythons `tempfile`-modul for å lage en unik, midlertidig mappe for hvert repo som skal analyseres.
-   **Kloning:** En `git clone`-kommando kjøres som en subprosess for å laste ned repoet inn i den midlertidige mappen.
-   **Opprydding:** En `finally`-blokk sikrer at den midlertidige mappen og alt innholdet slettes etter at analysen er ferdig (eller hvis en feil oppstår), for å unngå at disken fylles opp.
