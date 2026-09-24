from urllib.parse import urlparse


def is_doi_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        return (
            parsed.scheme.lower() in {"http", "https"}
            and parsed.hostname in {"doi.org", "dx.doi.org"}
            and parsed.path.lstrip("/").lower().startswith("10.")
        )
    except (AttributeError, ValueError):
        return False


# Function to resolve a doi url to the actual url. e.g. https://doi.org/10.5281/zenodo.1000000 -> https://zenodo.org/record/1000000
def resolve_doi_url(doi_url):
    import requests

    # Check if the input URL is a valid DOI URL
    if not is_doi_url(doi_url):
        raise ValueError("Invalid DOI URL. It should start with 'https://doi.org/'.")

    try:
        # Send a GET request to the DOI URL without following redirects
        response = requests.get(doi_url, allow_redirects=False)
        # Check if the response has a 'Location' header indicating a redirect
        if "Location" in response.headers:
            resolved_url = response.headers["Location"]
            return resolved_url
        else:
            raise ValueError("No redirect found for the DOI URL.")
    except requests.RequestException as e:
        raise ValueError(f"Error resolving DOI URL: {e}")


# Test cases
if __name__ == "__main__":
    test_cases = [
        "https://doi.org/10.1038/s41586-020-2649-2",
        "https://doi.org/10.5281/zenodo.17597120",
        "https://doi.org/10.5281/zenodo.18309441",
    ]

    for doi_url in test_cases:
        try:
            resolved_url = resolve_doi_url(doi_url)
            print(f"Resolved DOI URL: {doi_url} -> {resolved_url}")
        except ValueError as e:
            print(e)
