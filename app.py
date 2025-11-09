from flask import Flask, render_template, request
import os
import matplotlib
matplotlib.use('Agg')    # IMPORTANT for saving plots without a display
import matplotlib.pyplot as plt
import numpy as np
import requests
import lightkurve as lk

def resolve_star_id(star_id):
    nasa_url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
    q = f"select distinct hostname from ps where (hostname like 'Kepler%' or hostname like 'K2%') and st_id like '%{star_id}%'"
    params = {"query": q, "format": "json"}
    try:
        r = requests.get(nasa_url, params=params, timeout=40)
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0:
                return data[0]["hostname"]  # return the first match
    except Exception as e:
        print("Resolver error:", e)
    return star_id
# end here

app = Flask(__name__)

PLOT_DIR = os.path.join("static", "plots")
os.makedirs(PLOT_DIR, exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    planets = []
    plot_path = None

    if request.method == "POST":
        star_id = request.form.get("star_id", "").strip()
        resolved_id = resolve_star_id(star_id)
        try:
            threshold = float(request.form.get("threshold", 0.995))
        except:
            threshold = 0.995

        if not star_id:
            result = "Please enter a star ID (e.g. KIC 11446443)."
            return render_template("index.html", result=result)

        try:
            #  fetch light curve search results ---
            search_result = lk.search_lightcurve(star_id, mission="Kepler")
            if len(search_result) == 0:
                result = f"No Kepler light curve found for '{star_id}'. Try another ID."
                return render_template("index.html", result=result)

            # download first available light curve
            lc = search_result.download()
            # normalize (safely)
            try:
                lc = lc.normalize()
            except Exception:
                # sometimes the object is different; 
                lc.flux = lc.flux / np.nanmedian(lc.flux)

            # prepare the data
            brightness = lc.flux.value
            time = lc.time.value

            dips = brightness < threshold

            #  save plot 
            fname = "latest_plot.png"
            plot_path = os.path.join(PLOT_DIR, fname)

            plt.figure(figsize=(10,5))
            plt.plot(time, brightness, "k.", markersize=2, label="Brightness")
            plt.axhline(threshold, color="red", linestyle="--", label=f"Threshold {threshold}")
            if np.any(dips):
                plt.plot(time[dips], brightness[dips], "ro", markersize=4, label="Detected Dip")
            plt.xlabel("Time (days)")
            plt.ylabel("Normalized Brightness")
            plt.title(f"Light Curve for {star_id}")
            plt.legend()
            plt.tight_layout()
            plt.savefig(plot_path, bbox_inches="tight")
            plt.close()

            plot_path = f"/{plot_path.replace(os.path.sep, '/')}"


            #  result message 
            if np.any(dips):
                result = f"Possible transit event(s) detected in {star_id}!"
            else:
                result = f"No clear transit found for {star_id}."

            # --- query NASA Exoplanet Archive for confirmed planets ---
            q = f"select pl_name,hostname,pl_orbper,pl_rade from ps where hostname='{resolved_id}'"
            nasa_url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
            params = {"query": q, "format": "json"}
            try:
                r = requests.get(nasa_url, params=params, timeout=40)
                if r.status_code == 200:
                    planets = r.json()
                else:
                    planets = []
            except Exception:
                planets = []
                result+="Planet Data not available at the moment"

        except Exception as e:
            # it takes everything and show page for debugging
            result = f"Error while processing '{star_id}': {e}"

    return render_template("index.html", result=result, plot_path=plot_path, planets=planets)
if __name__ == "__main__":
        import os
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)

