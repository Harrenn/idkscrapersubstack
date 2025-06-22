import os
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from play import scrape_and_save

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET", "change-me")

DATA_DIR = "data"
COOKIE_PATH = os.path.join(DATA_DIR, "chrome_profile")  # just for existence check
DATE_PATH = os.path.join(DATA_DIR, "date.txt")

def get_current_date_filter():
    if os.path.exists(DATE_PATH):
        val = open(DATE_PATH).read().strip()
        return val if val else None
    return None

@app.route("/", methods=["GET"])
def index():
    # Show the menu with current date filter
    has_cookie = os.path.exists(COOKIE_PATH)
    cur_filter = get_current_date_filter()
    return render_template("index.html", has_cookie=has_cookie, current_date_filter=cur_filter)

@app.route("/set_date", methods=["POST"])
def set_date():
    date_val = request.form.get("date_filter", "").strip()
    if date_val:
        with open(DATE_PATH, "w") as f:
            f.write(date_val)
        flash(f"✅ Date filter set to: {date_val}", "success")
    else:
        flash("❌ Please enter a valid date filter.", "error")
    return redirect(url_for("index"))

@app.route("/clear_date", methods=["POST"])
def clear_date():
    if os.path.exists(DATE_PATH):
        os.remove(DATE_PATH)
    flash("✅ Date filter cleared.", "success")
    return redirect(url_for("index"))

@app.route("/extract", methods=["GET"])
def extract():
    # Calls play.py to generate the TXT and sends as download
    output = scrape_and_save()
    if not output:
        flash("⚠️ No new articles found (or not logged in).", "error")
        return redirect(url_for("index"))
    return send_file(output, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
