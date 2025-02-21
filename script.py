import re
from datetime import datetime
from scholarly import scholarly

# Define the professor's name
PROFESSOR_NAME = "Manuel Roveri"

# Define the comment markers in the HTML file
START_MARKER = "<!-- PUBLICATIONS_START -->"
END_MARKER = "<!-- PUBLICATIONS_END -->"

# Define the number of years to keep
CURRENT_YEAR = datetime.now().year
YEAR_THRESHOLD = CURRENT_YEAR - 10  # Last 10 years


def fetch_publications():
    """Fetches the publications from Google Scholar."""
    search_query = scholarly.search_author(PROFESSOR_NAME)
    author = next(search_query)  # Get first match
    author = scholarly.fill(author)  # Fetch full details

    publications = []
    
    for pub in author["publications"]:
        bib = pub.get("bib", {})
        year = bib.get("pub_year")
        venue = bib.get("citation", "Unknown Venue")

        # Skip entries without a year
        if not year or not year.isdigit():
            continue

        # Skip old entries
        year = int(year)
        if year <= YEAR_THRESHOLD:
            continue

        # Skip arXiv papers
        if "arXiv" in venue:
            continue

        pub = scholarly.fill(pub)
        bib = pub.get("bib", {})  # Take the in depth bib
        title = bib.get("title", "Unknown Title")
        authors = bib.get("author", "Unknown Authors")
        venue = bib.get("citation", "Unknown Venue")

        publications.append({"title": title, "year": year, "authors": authors, "venue": venue})

    # Sort by year (descending)
    publications.sort(key=lambda x: x["year"], reverse=True)

    return publications


def generate_html_list(publications):
    """Generates an HTML list for publications."""
    html_list = "\n".join(
        f'<li><strong>{pub["title"]}</strong><br>'
        f'<em>Authors:</em> {pub["authors"]}<br>'
        f'<em>Venue:</em> {pub["venue"]} ({pub["year"]})</li>'
        for pub in publications
    )
    return html_list


def update_publications_html(publications):
    """Updates the publications.html file with the new list."""
    with open("pages/publications.html", "r", encoding="utf-8") as file:
        content = file.read()

    # Find the markers in the HTML file
    start_index = content.find(START_MARKER)
    end_index = content.find(END_MARKER)

    if start_index == -1 or end_index == -1:
        raise ValueError("Markers not found in publications.html")

    # Generate the updated publication list
    new_publications_html = generate_html_list(publications)

    # Replace the content between the markers
    updated_content = (
        content[: start_index + len(START_MARKER)]
        + "\n<ul>\n"
        + new_publications_html
        + "\n</ul>\n"
        + content[end_index:]
    )

    # Write back the modified HTML
    with open("pages/publications.html", "w", encoding="utf-8") as file:
        file.write(updated_content)


if __name__ == "__main__":
    # Fetch, process, and update the publications
    publications = fetch_publications()
    update_publications_html(publications)
    print("Publications updated successfully!")