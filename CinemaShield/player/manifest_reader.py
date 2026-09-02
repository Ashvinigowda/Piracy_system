import json

MANIFEST_PATH = "../backend/manifest.json"

def load_manifest():
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)

if __name__ == "__main__":
    manifest = load_manifest()
    print("Movie ID:", manifest.get("movie_id"))
    print("Total shards:", len(manifest["shards"]))
