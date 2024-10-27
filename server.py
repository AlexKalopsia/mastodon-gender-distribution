import logging
import os
import requests

from authlib.integrations.flask_client import (
    OAuth,
    OAuthError,
)  # pip install Authlib
from flask import (  # pip install Flask
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from mastodon import Mastodon, MastodonNotFoundError
from wtforms import Form, SelectField, StringField  # pip install WTForms

from analyze import (
    Cache,
    analyze_followers,
    analyze_following,
    analyze_timeline,
    div,
    dry_run_analysis,
    get_mastodon_api,
    get_user_from_handle,
    parse_mastodon_handle,
    get_following_lists,
)

logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

APP_NAME = "mastodon-gender-distribution"
TRACKING_ID = os.environ.get("TRACKING_ID")

app = Flask(APP_NAME)
app.config["SECRET_KEY"] = os.environ["COOKIE_SECRET"]  # TODO: encrypt
app.config["DRY_RUN"] = False

oauth = OAuth(app)


@app.route("/login")
def login():
    # Get instance from login field
    handle = request.args.get("handle", "alexkalopsia@mastodon.social")
    _, instance = parse_mastodon_handle(handle)

    metadata = None

    try:
        response = requests.get(
            f"https://{instance}/.well-known/openid-configuration"
        )
        response.raise_for_status()
        metadata = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch metadata: {e}")

    token_endpoint = (
        metadata.get("token_endpoint")
        if metadata
        else f"https://{instance}/oauth/token"
    )
    auth_endpoint = (
        metadata.get("authorization_endpoint")
        if metadata
        else f"https://{instance}/oauth/authorize"
    )

    client_id, client_secret = Mastodon.create_app(
        "mastodon-gender-distribution",
        api_base_url=instance,
        redirect_uris=[
            "urn:ietf:wg:oauth:2.0:oob",
            "http://127.0.0.1:8000/authorized",
            f"https://{instance}/authorized",
        ],
    )

    app.config["MASTODON_CLIENT_ID"] = client_id
    app.config["MASTODON_CLIENT_SECRET"] = client_secret
    app.config["MASTODON_INSTANCE"] = instance
    session["client_id"] = client_id
    session["client_secret"] = client_secret
    session["instance"] = instance

    # Register client
    oauth.register(
        name="mastodon",
        api_base_url=f"https://{instance}/api/v1",
        access_token_url=token_endpoint,
        authorize_url=auth_endpoint,
        client_id=client_id,
        client_secret=client_secret,
        client_kwargs={"scope": "read"},
        fetch_token=lambda: session.get("token"),  # DON'T DO IT IN PRODUCTION
    )

    redirect_uri = url_for(
        "oauth_authorized",
        client_id=client_id,
        client_secret=client_secret,
        handle=handle,
        _external=True,
    )
    return oauth.mastodon.authorize_redirect(redirect_uri)


@app.route("/logout")
def logout():
    session.pop("mastodon_token")
    session.pop("mastodon_user")
    flash("Logged out.")
    return redirect("/")


@app.errorhandler(OAuthError)
def handle_error(error):
    flash("You denied the request to sign in.")
    return redirect("/")


@app.route("/authorized")
def oauth_authorized():

    args = request.args
    handle = args.get("handle")

    _, instance = parse_mastodon_handle(handle)

    tok = oauth.mastodon.authorize_access_token()
    response = oauth.mastodon.get(
        f"https://{instance}/api/v1/accounts/verify_credentials"
    )

    print("Response status:", response.status_code)
    print("Response text:", response.text)

    try:
        profile = response.json()
    except ValueError as e:
        print("JSON decode error:", e)
        return "Failed to decode JSON response"

    session["mastodon_token"] = tok["access_token"]
    session["mastodon_user"] = profile["acct"]

    try:
        session["lists"] = get_following_lists(
            profile["id"],
            tok["access_token"],
            instance,
        )
        print("LISTS:")
        print(session["lists"])
    except Exception:
        app.logger.exception("Error in get_following_lists, ignoring")
        session["lists"] = []

    return redirect(url_for("index"))


class LoginForm(Form):
    login_acct = StringField("Mastodon user handle")


class AnalyzeForm(Form):
    analyze_acct = StringField("Mastodon user handle")
    lst = SelectField("List")


@app.route("/", methods=["GET", "POST"])
def index():
    tok = session.get("mastodon_token")

    if session.get("mastodon_user"):
        form = AnalyzeForm(request.form)
    else:
        form = LoginForm(request.form)

    print("ANALYZE - LISTS")
    print(session.get("lists"))

    form_type = request.form.get("form_type")
    print(f"TYPE {form_type}")
    if form_type == "analyze":
        if session.get("lists"):
            form.lst.choices = [("none", "No list")] + [
                (str(list["id"]), list["name"]) for list in session["lists"]
            ]
            print("LISTS UPDATED")
        else:
            del form.lst

        different_user = form.analyze_acct.data != session.get("mastodon_user")

        results = {}
        list_name = list_id = error = None

    if request.method == "POST":
        form_type = request.form.get("form_type")
        if form_type == "login":

            handle = form.login_acct.data
            _, _ = parse_mastodon_handle(handle)

            return render_template(
                "index.html",
                form=form,
                div=div,
                TRACKING_ID=TRACKING_ID,
            )
        elif form_type == "analyze":

            handle = form.analyze_acct.data
            _, instance = parse_mastodon_handle(handle)

            if form.validate() and form.analyze_acct.data:
                # Don't show auth'ed user's lists in results for another user.
                if hasattr(form, "lst") and different_user:
                    del form.lst

                if app.config["DRY_RUN"]:
                    list_name = None
                    following, followers, timeline = dry_run_analysis()
                    results = {
                        "following": following,
                        "followers": followers,
                        "timeline": timeline,
                    }
                else:
                    if (
                        session.get("lists")
                        and form.lst
                        and form.lst.data != "none"
                    ):
                        list_id = int(form.lst.data)
                        list_name = [
                            list["name"]
                            for list in session["lists"]
                            if int(list["id"]) == list_id
                        ][0]

                    try:
                        api = get_mastodon_api(tok, instance)
                        cache = Cache()

                        user = get_user_from_handle(
                            form.analyze_acct.data, api
                        )

                        if different_user and user.indexable is False:
                            raise Exception(
                                f"User {form.analyze_acct.data} is not indexable.\n"
                                f"If the account is yours, you can change the setting on: "
                                f"Settings > Public profile > Privacy and reach > "
                                f"Include public posts in search results"
                            )

                        results = {
                            "following": analyze_following(
                                user.id, list_id, api, cache
                            ),
                            "followers": analyze_followers(
                                user.id, api, cache
                            ),
                            "timeline": analyze_timeline(
                                user.id, list_id, api, cache
                            ),
                        }
                        for key, value in results.items():
                            if not value:
                                raise Exception(
                                    f"Failed to fetch results "
                                    f"for user {form.analyze_acct.data}."
                                )
                    except Exception as exc:
                        import traceback

                        traceback.print_exc()
                        if isinstance(exc, MastodonNotFoundError):
                            error = f"Could not find user {form.analyze_acct.data}."
                        else:
                            error = exc

                    if error is not None:
                        error = str(error).replace("\n", "<br>")

            return render_template(
                "index.html",
                form=form,
                results=results,
                error=error,
                div=div,
                list_name=list_name,
                TRACKING_ID=TRACKING_ID,
            )
    return render_template(
        "index.html",
        form=form,
        div=div,
        TRACKING_ID=TRACKING_ID,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("port", nargs="?", type=int)
    args = parser.parse_args()

    if args.port is None:
        port = int(os.environ.get("PORT", 8000))
    else:
        port = args.port

    app.config["DRY_RUN"] = args.dry_run
    app.run(port=port, debug=args.debug)
