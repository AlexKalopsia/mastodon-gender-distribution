import os
import pickle
import random
import re
import sys
import time
import warnings
import webbrowser

import gender_guesser.detector as gender
from mastodon import (
    Mastodon,
)
from requests_oauthlib import OAuth2Session
from unidecode import unidecode

if os.path.exists("detector.pickle"):
    detector = pickle.load(open("detector.pickle", "rb"))
else:
    detector = gender.Detector(case_sensitive=False)
    with open("detector.pickle", "wb+") as f:
        pickle.dump(detector, f)


class User:
    def __init__(
        self,
        id=None,
        username=None,
        acct=None,
        display_name=None,
        locked=False,
        bot=False,
        discoverable=False,
        indexable=False,
        group=False,
        created_at=None,
        note=None,
        url=None,
        uri=None,
        avatar=None,
        avatar_static=None,
        header=None,
        header_static=None,
        followers_count=0,
        following_count=0,
        statuses_count=0,
        last_status_at=None,
        hide_collections=False,
        noindex=False,
        emojis=None,
        roles=None,
        fields=None,
        moved=False,
        limited=False,
        suspended=False,
        avatar_remote_url=None,
    ):
        self.id = id
        self.username = username
        self.acct = acct
        self.display_name = display_name
        self.locked = locked
        self.bot = bot
        self.discoverable = discoverable
        self.indexable = indexable
        self.group = group
        self.created_at = created_at
        self.note = note
        self.url = url
        self.uri = uri
        self.avatar = avatar
        self.avatar_static = avatar_static
        self.header = header
        self.header_static = header_static
        self.followers_count = followers_count
        self.following_count = following_count
        self.statuses_count = statuses_count
        self.last_status_at = last_status_at
        self.hide_collections = hide_collections
        self.noindex = noindex
        self.emojis = emojis
        self.roles = roles
        self.fields = fields
        self.moved = moved
        self.limited = limited
        self.suspended = suspended
        self.avatar_remote_url = avatar_remote_url


def split(s):
    try:
        return s.split()[0]
    except IndexError:
        return s


def rm_punctuation(s, _pat=re.compile(r"\W+")):
    return _pat.sub(" ", s)


def make_pronoun_patterns():
    for p, g in [
        ("non binary", "nonbinary"),
        ("non-binary", "nonbinary"),
        ("nonbinary", "nonbinary"),
        ("enby", "nonbinary"),
        ("nb", "nonbinary"),
        ("genderqueer", "nonbinary"),
        ("man", "male"),
        ("male", "male"),
        ("boy", "male"),
        ("guy", "male"),
        ("woman", "female"),
        ("womanist", "female"),
        ("female", "female"),
        ("girl", "female"),
        ("gal", "female"),
        ("latina", "female"),
        ("latino", "male"),
        ("dad", "male"),
        ("mum", "female"),
        ("mom", "female"),
        ("father", "male"),
        ("grandfather", "male"),
        ("mother", "female"),
        ("grandmother", "female"),
        ("they", "nonbinary"),
        ("xe", "nonbinary"),
        ("xi", "nonbinary"),
        ("xir", "nonbinary"),
        ("ze", "nonbinary"),
        ("zie", "nonbinary"),
        ("zir", "nonbinary"),
        ("hir", "nonbinary"),
        ("she", "female"),
        ("hers", "female"),
        ("her", "female"),
        ("he", "male"),
        ("his", "male"),
        ("him", "male"),
    ]:
        for text in (
            r"\b" + p + r"\b",
            r"\b" + p + r"/",
            r"\b" + p + r" /",
            r"pronoun\.is/" + p,
        ):
            yield re.compile(text), g


_PRONOUN_PATTERNS = list(make_pronoun_patterns())


class Cache(object):
    def __init__(self):
        self._users = {}
        self._hits = self._misses = 0

    @property
    def hit_percentage(self):
        total_requests = self._hits + self._misses
        if total_requests == 0:
            return 0
        return (100 * self._hits) / total_requests

    def UsersLookup(self, user_ids):
        """
        Looks for cached users by their ids
        """
        users = [self._users[uid] for uid in user_ids if uid in self._users]
        self._hits += len(users)
        self._misses += len(user_ids) - len(users)
        return users

    def UncachedUsers(self, user_ids):
        """
        Given a list of user IDs, it returns the ones that are not in the cache

        Example:
            >>> self._users = {108192926138721866: {"username": "alexkalopsia"},
            109322706099399045: {"username": "jessejiryudavis"}}
        """
        uncached_ids = set(user_ids) - set(self._users)
        return list(uncached_ids)

    def AddUsers(self, users):
        """
        Add a list of user objects to the cache, storing each user
        with a key relative to their id.

        Example:
            >>> {108192926138721866: {"username": "alexkalopsia"}}
        """
        for user in users:
            self._users[user.id] = user


def declared_gender(description):
    dl = description.lower()
    if (
        "pronoun.is" in dl
        and "pronoun.is/she" not in dl
        and "pronoun.is/he" not in dl
    ):
        return "nonbinary"

    guesses = set()
    for p, g in _PRONOUN_PATTERNS:
        if p.search(dl):
            guesses.add(g)
            if len(guesses) > 1:
                return "andy"  # Several guesses: don't know.

    if len(guesses) == 1:
        return next(iter(guesses))

    return "andy"  # Zero or several guesses: don't know.


def analyze_user(user, verbose=False):
    """Get (gender, declared) tuple.

    gender is "male", "female", "nonbinary", or "andy" meaning unknown.
    declared is True or False.
    """
    with warnings.catch_warnings():
        # Suppress unidecode warning "Surrogate character will be ignored".
        warnings.filterwarnings("ignore")

        # Look for explicit Pronouns field, otherwise check bio
        pronouns_field = next(
            (
                field["value"]
                for field in user.fields
                if "Pronouns" in field.get("name")
            ),
            None,
        )
        description = (
            pronouns_field if pronouns_field is not None else user.note
        )
        g = declared_gender(description)

        if g != "andy":
            return g, True

        # We haven't found a preferred pronoun.
        for name, country in [
            (split(user.display_name), "usa"),
            (user.display_name, "usa"),
            (split(unidecode(user.display_name)), "usa"),
            (unidecode(user.display_name), "usa"),
            (split(user.display_name), None),
            (user.display_name, None),
            (unidecode(user.display_name), None),
            (split(unidecode(user.display_name)), None),
        ]:
            g = detector.get_gender(name, country)
            if g != "andy":
                # Not androgynous.
                break

            g = detector.get_gender(rm_punctuation(name), country)
            if g != "andy":
                # Not androgynous.
                break

        if verbose:
            print(
                "{:20s}\t{:40s}\t{:s}".format(
                    user.username.encode("utf-8"),
                    user.display_name.encode("utf-8"),
                    g,
                )
            )

        if g.startswith("mostly_"):
            g = g.split("mostly_")[1]

        return g, False


def div(num, denom):
    if denom:
        return num / float(denom)

    return 0


class Stat(object):
    def __init__(self):
        self.n = 0
        self.n_declared = 0


class Analysis(object):
    def __init__(self, ids_sampled, ids_fetched):
        self.nonbinary = Stat()
        self.male = Stat()
        self.female = Stat()
        self.andy = Stat()
        self.ids_sampled = ids_sampled
        self.ids_fetched = ids_fetched

    def update(self, gender, declared):
        # Elide gender-unknown and androgynous names.
        attr = getattr(self, "andy" if gender == "unknown" else gender)
        attr.n += 1
        if declared:
            attr.n_declared += 1

    def guessed(self, gender=None):
        if gender:
            attr = getattr(self, gender)
            return attr.n - attr.n_declared

        return (
            self.guessed("nonbinary")
            + self.guessed("male")
            + self.guessed("female")
        )

    def declared(self, gender=None):
        if gender:
            attr = getattr(self, gender)
            return attr.n_declared

        return (
            self.nonbinary.n_declared
            + self.male.n_declared
            + self.female.n_declared
        )

    def pct(self, gender):
        attr = getattr(self, gender)
        return div(
            100 * attr.n, self.nonbinary.n + self.male.n + self.female.n
        )


def dry_run_analysis():
    following = Analysis(250, 400)
    following.nonbinary.n = 10
    following.nonbinary.n_declared = 10
    following.male.n = 200
    following.male.n_declared = 20
    following.female.n = 40
    following.female.n_declared = 5
    following.andy.n = 250

    followers = Analysis(250, 400)
    followers.nonbinary.n = 10
    followers.nonbinary.n_declared = 10
    followers.male.n = 200
    followers.male.n_declared = 20
    followers.female.n = 40
    followers.female.n_declared = 5
    followers.andy.n = 250

    timeline = Analysis(250, 400)
    timeline.nonbinary.n = 10
    timeline.nonbinary.n_declared = 10
    timeline.male.n = 200
    timeline.male.n_declared = 20
    timeline.female.n = 40
    timeline.female.n_declared = 5
    timeline.andy.n = 250

    boosts = Analysis(250, 400)
    boosts.nonbinary.n = 10
    boosts.nonbinary.n_declared = 10
    boosts.male.n = 200
    boosts.male.n_declared = 20
    boosts.female.n = 40
    boosts.female.n_declared = 5
    boosts.andy.n = 250

    replies = Analysis(250, 400)
    replies.nonbinary.n = 10
    replies.nonbinary.n_declared = 10
    replies.male.n = 200
    replies.male.n_declared = 20
    replies.female.n = 40
    replies.female.n_declared = 5
    replies.andy.n = 250

    mentions = Analysis(250, 400)
    mentions.nonbinary.n = 10
    mentions.nonbinary.n_declared = 10
    mentions.male.n = 200
    mentions.male.n_declared = 20
    mentions.female.n = 40
    mentions.female.n_declared = 5
    mentions.andy.n = 250

    return following, followers, timeline, boosts, replies, mentions


def analyze_users(users, ids_fetched=None):
    an = Analysis(ids_sampled=len(users), ids_fetched=ids_fetched)

    for user in users:
        g, declared = analyze_user(user)
        an.update(g, declared)

    return an


def batch(it, size):
    for i in range(0, len(it), size):
        yield it[i : i + size]


def get_mastodon_api(access_token, instance="mastodon.social"):
    return Mastodon(
        access_token=access_token, api_base_url=f"https://{instance}"
    )


# 80 ids per call (total 800).
MAX_GET_FOLLOWING_IDS_CALLS = 10
MAX_GET_FOLLOWER_IDS_CALLS = 10

# 100 users per call.
MAX_USERS_LOOKUP_CALLS = 30
MAX_TIMELINE_CALLS = 10


def get_following_lists(user_id, access_token, instance):
    api = get_mastodon_api(access_token, instance)

    # Only store what we need, avoid oversized session cookie.
    def process_lists():
        for list in reversed(api.lists()):
            yield {
                "id": list.get("id"),
                "name": list.get("title"),
            }

    return list(process_lists())


def analyze_self(handle, api):
    user = get_user_from_handle(handle, api)
    return analyze_user(user)


def fetch_users(users, cache):
    fetched_users = []

    user_ids = [user.id for user in users]
    cached_users = cache.UsersLookup(user_ids)

    # Add cached users
    fetched_users.extend(cached_users)

    # Add uncached users
    uncached_users = [
        user
        for user in users
        if user.id not in {cached_user.id for cached_user in cached_users}
    ]
    cache.AddUsers(uncached_users)
    fetched_users.extend(uncached_users)

    return users


def analyze_following(user_id, list_id, api, cache):

    following_accounts = []

    if list_id is not None:
        accounts = api.list_accounts(id=list_id, limit=80)
    else:
        accounts = api.account_following(id=user_id, limit=80)

    for _ in range(MAX_GET_FOLLOWING_IDS_CALLS - 1):
        if not accounts:
            break

        following_accounts.extend(accounts)

        accounts = api.fetch_next(accounts)

        if accounts is None:
            break

    if following_accounts is None:
        return Analysis(0, 0)

    # Get a maximum of 3000 users (randomly sampled)
    if len(following_accounts) > 100 * MAX_USERS_LOOKUP_CALLS:
        following_sample = random.sample(
            following_accounts, 100 * MAX_USERS_LOOKUP_CALLS
        )
    else:
        following_sample = following_accounts

    users = fetch_users(following_sample, cache)
    return analyze_users(users, ids_fetched=len(following_sample))


def analyze_followers(user_id, api, cache):

    follower_accounts = []
    accounts = api.account_followers(id=user_id, limit=80)

    for _ in range(MAX_GET_FOLLOWER_IDS_CALLS - 1):
        if not accounts:
            break

        follower_accounts.extend(accounts)

        accounts = api.fetch_next(accounts)

        if accounts is None:
            break

    if follower_accounts is None:
        return Analysis(0, 0)

    # Get a maximum of 3000 users (randomly sampled)
    if len(follower_accounts) > 100 * MAX_USERS_LOOKUP_CALLS:
        followers_sample = random.sample(
            follower_accounts, 100 * MAX_USERS_LOOKUP_CALLS
        )
    else:
        followers_sample = follower_accounts

    # Sample of 40
    users = fetch_users(followers_sample, cache)
    return analyze_users(users, ids_fetched=len(followers_sample))


"""
Analyze the timeline containing the user's following and followers' toots
"""


def analyze_timeline(user_id, list_id, api, cache):
    # Timeline-functions are limited to 40 statuses
    timeline_accounts = []

    if list_id is not None:
        statuses = api.timeline_list(id=list_id, limit=40)
    else:
        statuses = api.timeline_home(limit=40)

    # Max 400 toots, 40 at a time.
    for _ in range(MAX_TIMELINE_CALLS):
        if not statuses:
            break

        timeline_accounts.extend(
            [s.account for s in statuses if s.account.id != user_id]
        )

        statuses = api.fetch_next(statuses)

        if statuses is None:
            break

    if not timeline_accounts:
        return Analysis(0, 0)

    # Reduce to unique list of ids
    timeline_accounts = list(timeline_accounts)
    users = fetch_users(timeline_accounts, cache)
    return analyze_users(users, ids_fetched=len(timeline_accounts))


"""
Analyze the timeline containing the user's own toots.
This method is never called when deploying the server. 
"""


def analyze_my_timeline(user_id, api, cache):
    timeline_ids = []

    # Timeline-functions are limited to 40 statuses
    statuses = api.timeline_home(limit=40)

    # Max 400 toots, 40 at a time.
    for _ in range(1, MAX_TIMELINE_CALLS):

        if not statuses:
            break

        timeline_ids.extend(
            [s.account.id for s in statuses if s.account.id != user_id]
        )

        statuses = api.fetch_next(statuses)

        if statuses is None:
            break

    reblog_ids = []
    reply_ids = []
    timeline_ids = []
    # TODO: This is from Twitter and doesn't match Mastodon statuses
    for s in statuses:
        if s.reblog is not None:
            reblog_ids.append(s.reblog.account.id)
        elif s.in_reply_to_id is not None:
            for i in s.mentions:
                reply_ids.append(i.id)
        elif len(s.mentions) > 0:
            for i in s.mentions:
                timeline_ids.append(i.id)

    outdict = {
        "boosts": reblog_ids,
        "replies": reply_ids,
        "mentions": timeline_ids,
    }
    # newdict = {}
    # for ids in outdict.keys():
    #    users = fetch_users(outdict.get(ids), cache)
    #    newdict[ids] = analyze_users(users, ids_fetched=len(outdict.get(ids)))
    return outdict


def get_access_token(client_id, client_secret, instance):
    AUTHORIZATION_URL = f"https://{instance}/oauth/authorize"
    TOKEN_URL = f"https://{instance}/oauth/token"
    REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"

    oauth_client = OAuth2Session(
        client_id, redirect_uri=REDIRECT_URI, scope=["read"]
    )

    print("\nAuthorizing on Mastodon...\n")
    url, state = oauth_client.authorization_url(AUTHORIZATION_URL)
    print(
        "I will try to start a browser to visit the following Mastodon page."
        "\nIf a browser does not start, copy the URL to your browser, "
        "accept the request, and retrieve the pincode to be used "
        "in the next step to obtaining an Authentication Token: \n"
        f"\n\t{url}\n"
    )
    webbrowser.open(url)
    code = input("Enter yout authorization code: ")

    print("\nGenerating and signing request for an access token...\n")

    resp = f"https://{instance}/oauth/authorize/native?code={code}"

    try:
        token = oauth_client.fetch_token(
            TOKEN_URL,
            authorization_response=resp,
            client_secret=client_secret,
        )
    except ValueError as e:
        msg = (
            "Invalid response from Mastodon requesting " "temp token: {0}"
        ).format(e)
        raise ValueError(msg)

    #
    # print('''Your tokens/keys are as follows:
    #     client_id         = {ck}
    #     client_secret      = {cs}
    #     access_token_key     = {atk}
    #     access_token_secret  = {ats}'''.format(
    #     ck=client_id,
    #     cs=client_secret,
    #     atk=resp.get('access_token'),
    #     ats=resp.get('access_token_secret')))

    print(f"\nAccess Token: {token['access_token']}")

    return token["access_token"]


def parse_mastodon_handle(handle):
    handle = handle.lstrip("@")
    if "@" in handle:
        username, instance = handle.split("@", 1)
    else:
        username = handle
        instance = None

    return username, instance


def get_user_from_handle(handle, api):
    username, _ = parse_mastodon_handle(handle)
    accounts = api.account_search(username, limit=1)

    if accounts:
        account = accounts[0]
        return account
    else:
        return None


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="Estimate gender distribution of "
        "Mastodon following accounts, followers and"
        "your timeline"
    )
    p.add_argument("user_handle", nargs=1)
    p.add_argument(
        "--self",
        help="perform gender analysis on own user handle",
        action="store_true",
    )
    p.add_argument("--dry-run", help="fake results", action="store_true")
    args = p.parse_args()
    [user_handle] = args.user_handle

    username, instance = parse_mastodon_handle(user_handle)

    client_id = os.environ.get("CLIENT_KEY") or input(
        "Enter your client key: "
    )

    client_secret = os.environ.get("CLIENT_SECRET") or input(
        "Enter your client secret: "
    )

    if instance is None:
        instance = input("Enter your Mastodon instance: ")

    if args.dry_run:
        tok = None
    else:
        tok = get_access_token(client_id, client_secret, instance)

    if args.self:
        if args.dry_run:
            g, declared = "male", True
        else:
            api = get_mastodon_api(tok, instance)
            g, declared = analyze_self(user_handle, api)

        print("{} ({})".format(g, "declared pronoun" if declared else "guess"))
        sys.exit()

    print(
        "{:>25s}\t{:>10s}\t{:>10s}\t{:>10s}\t{:>10s}".format(
            "", "NONBINARY", "MEN", "WOMEN", "UNKNOWN"
        )
    )

    start = time.time()
    cache = Cache()
    if args.dry_run:
        following, followers, timeline, boosts, replies, mentions = (
            dry_run_analysis()
        )
    else:
        api = get_mastodon_api(tok, instance)
        user_id = get_user_from_handle(user_handle, api).id
        following = analyze_following(user_id, None, api, cache)
        followers = analyze_followers(user_id, api, cache)
        timeline = analyze_timeline(user_id, None, api, cache)
        # TODO: implement Mastodon-compatible analyze_my_timeline
        # mytimeline = analyze_my_timeline(user_id, api, cache)
        # boosts = mytimeline.get("boosts")
        # replies = mytimeline.get("replies")
        # mentions = mytimeline.get("mentions")

    duration = time.time() - start

    for user_type, an in [
        ("following", following),
        ("followers", followers),
        ("timeline", timeline),
        # ("boosts", boosts),
        # ("replies", replies),
        # ("mentions", mentions),
    ]:

        # Check if the list is empty
        if not an:  # If an is an empty list
            print(f"{user_type.capitalize()} data is empty.")
            print(
                "{:>25s}\t{:>10s}\t{:>10s}\t{:>10s}".format(
                    "User Type", "Nonbinary", "Male", "Female"
                )
            )
            print(
                "{:>25s}\t{:>10d}\t{:>10d}\t{:>10d}".format(
                    "Guessed from name:", 0, 0, 0
                )
            )
            print(
                "{:>25s}\t{:>10d}\t{:>10d}\t{:>10d}".format(
                    "Declared pronouns:", 0, 0, 0
                )
            )
            print("\n")
            continue  # Skip to the next iteration

        nb, men, women, andy = (
            an.nonbinary.n,
            an.male.n,
            an.female.n,
            an.andy.n,
        )

        print(
            "{:>25s}\t{:>10.2f}%\t{:10.2f}%\t{:10.2f}%".format(
                user_type,
                an.pct("nonbinary"),
                an.pct("male"),
                an.pct("female"),
            )
        )

        print(
            "{:>25s}\t{:>10d} \t{:10d} \t{:10d} \t{:10d}".format(
                "Guessed from name:",
                an.guessed("nonbinary"),
                an.guessed("male"),
                an.guessed("female"),
                an.andy.n,
            )
        )

        print(
            "{:>25s}\t{:>10d} \t{:10d} \t{:10d}".format(
                "Declared pronouns:",
                an.declared("nonbinary"),
                an.declared("male"),
                an.declared("female"),
            )
        )
        print("\n")

    print("")
    print(
        "Analysis took {:.2f} seconds, cache hit ratio {}%".format(
            duration, cache.hit_percentage
        )
    )
