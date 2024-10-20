import os
import pickle
import random
import re
import sys
import time
import warnings
import webbrowser

import gender_guesser.detector as gender  # pip install gender-guesser
from mastodon import Mastodon  # pip install Mastodon.py
from requests_oauthlib import OAuth2Session  # pip install requests-oauthlib
from unidecode import unidecode  # pip install unidecode

if os.path.exists("detector.pickle"):
    detector = pickle.load(open("detector.pickle", "rb"))
else:
    detector = gender.Detector(case_sensitive=False)
    with open("detector.pickle", "wb+") as f:
        pickle.dump(detector, f)


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
        return (100 * self._hits) / (self._hits + self._misses)

    def UsersLookup(self, user_ids):
        rv = [self._users[uid] for uid in user_ids if uid in self._users]
        self._hits += len(rv)
        self._misses += len(user_ids) - len(rv)
        return rv

    def UncachedUsers(self, user_ids):
        return list(set(user_ids) - set(self._users))

    def AddUsers(self, profiles):
        for p in profiles:
            self._users[p.id] = p


def declared_gender(description):
    dl = description.lower()
    if "pronoun.is" in dl and "pronoun.is/she" not in dl and "pronoun.is/he" not in dl:
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
        g = declared_gender(user.description)
        if g != "andy":
            return g, True

        # We haven't found a preferred pronoun.
        for name, country in [
            (split(user.name), "usa"),
            (user.name, "usa"),
            (split(unidecode(user.name)), "usa"),
            (unidecode(user.name), "usa"),
            (split(user.name), None),
            (user.name, None),
            (unidecode(user.name), None),
            (split(unidecode(user.name)), None),
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
                    user.screen_name.encode("utf-8"), user.name.encode("utf-8"), g
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

        return self.guessed("nonbinary") + self.guessed("male") + self.guessed("female")

    def declared(self, gender=None):
        if gender:
            attr = getattr(self, gender)
            return attr.n_declared

        return self.nonbinary.n_declared + self.male.n_declared + self.female.n_declared

    def pct(self, gender):
        attr = getattr(self, gender)
        return div(100 * attr.n, self.nonbinary.n + self.male.n + self.female.n)


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

    return following, followers, timeline


def analyze_users(users, ids_fetched=None):
    an = Analysis(ids_sampled=len(users), ids_fetched=ids_fetched)

    for user in users:
        g, declared = analyze_user(user)
        an.update(g, declared)

    return an


def batch(it, size):
    for i in range(0, len(it), size):
        yield it[i : i + size]


def get_mastodon_api(client_id, client_secret, access_token, instance_name="mastodon.social"):
    return Mastodon(
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        api_base_url=f"https://{instance_name}"
    )


# 5000 ids per call.
MAX_GET_FOLLOWING_IDS_CALLS = 10
MAX_GET_FOLLOWER_IDS_CALLS = 10

# 100 users per call.
MAX_USERS_LOOKUP_CALLS = 30


def get_following_lists(
    user_id, client_id, client_secret, access_token, access_token_secret, instance_name
):
    api = get_mastodon_api(
        client_id, client_secret, access_token, access_token_secret, instance_name
    )

    # Only store what we need, avoid oversized session cookie.
    def process_lists():
        for list in reversed(api.account_lists(id=user_id)):
            as_dict = list.AsDict()
            yield {"id": as_dict.get("id"), "name": as_dict.get("name")}

    return list(process_lists())


def analyze_self(api):
    return api.me()


def fetch_users(user_ids, api, cache):
    users = []
    accounts_info = []
    users.extend(cache.UsersLookup(user_ids))
    for ids in batch(cache.UncachedUsers(user_ids), 100):
        # Do here
        for user_id in user_ids:
            
            account_info = api.account(id=user_id)
            accounts_info.append(account_info)

        results = accounts_info
        cache.AddUsers(results)
        users.extend(results)

    return users


def analyze_following(user_id, list_id, api, cache):
    following_ids = []
    for _ in range(MAX_GET_FOLLOWING_IDS_CALLS):
        if list_id is not None:
            print(f"LIST {list_id}")
            data = api.list_accounts(id=list_id)
            print(data)
            following_ids.extend([fr.id for fr in data])
        else:
            data = api.account_following(id=user_id)
            print("NO LIST!! GETTING FOLLOWING ACCOUNTS")
            print(data)
            following_ids.extend(data)

    # We can fetch users' details 100 at a time.
    if len(following_ids) > 100 * MAX_USERS_LOOKUP_CALLS:
        following_id_sample = random.sample(following_ids, 100 * MAX_USERS_LOOKUP_CALLS)
    else:
        following_id_sample = following_ids

    users = fetch_users(following_id_sample, api, cache)
    return analyze_users(users, ids_fetched=len(following_ids))


def analyze_followers(user_id, api, cache):
    follower_ids = []
    for _ in range(MAX_GET_FOLLOWER_IDS_CALLS):
        data = api.account_followers(id=user_id)
        follower_ids.extend(data)

    # We can fetch users' details 100 at a time.
    if len(follower_ids) > 100 * MAX_USERS_LOOKUP_CALLS:
        follower_id_sample = random.sample(follower_ids, 100 * MAX_USERS_LOOKUP_CALLS)
    else:
        follower_id_sample = follower_ids

    users = fetch_users(follower_id_sample, api, cache)
    return analyze_users(users, ids_fetched=len(follower_ids))


def analyze_timeline(user_id, list_id, api, cache):
    # Timeline-functions are limited to 200 statuses
    if list_id is not None:
        statuses = api.timeline_list(id=list_id, limit=200)
    else:
        statuses = api.timeline_home(limit=200)

    timeline_ids = []
    for s in statuses:
        # Skip the current user's own tweets.
        if s.user.screen_name != user_id:
            timeline_ids.append(s.user.id)

    # Reduce to unique list of ids
    timeline_ids = list(set(timeline_ids))
    users = fetch_users(timeline_ids, api, cache)
    return analyze_users(users, ids_fetched=len(timeline_ids))


def analyze_my_timeline(user_id, api, cache):
    # Timeline-functions are limited to 200 statuses
    statuses = api.timeline (
        limit=200,
    )
    print("MY STATUSES")
    print(statuses)
    max_id = 0
    # Max 2000 tweets.
    for i in range(1, 10):
        if max_id == statuses[-1].id - 1:
            # Already fetched all tweets in timeline.
            break
        max_id = statuses[-1].id - 1
        statuses = statuses + api.timeline(
            limit=200,
            max_id=max_id
        )
    boost_ids = []
    reply_ids = []
    timeline_ids = []
    for s in statuses:
        print(s)
        if s.retweeted_status is not None:
            boost_ids.append(s.retweeted_status.user.id)
        elif s.in_reply_to_status_id is not None:
            for i in s.user_mentions:
                reply_ids.append(i.id)
        elif len(s.user_mentions) > 0:
            for i in s.user_mentions:
                timeline_ids.append(i.id)

    outdict = {
        "boosts": boost_ids,
        "replies": reply_ids,
        "mentions": timeline_ids,
    }
    newdict = {}
    for ids in outdict.keys():
        users = fetch_users(outdict.get(ids), api, cache)
        newdict[ids] = analyze_users(users, ids_fetched=len(outdict.get(ids)))
    return newdict

def get_access_token(client_id, client_secret, instance_name):
    AUTHORIZATION_URL = f"https://{instance_name}/oauth/authorize"
    TOKEN_URL = f"https://{instance_name}/oauth/token"
    REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"

    oauth_client = OAuth2Session(
        client_id, redirect_uri=REDIRECT_URI, scope=['read']
    )

    print("\nAuthorizing on Mastodon...\n")
    url, state = oauth_client.authorization_url(AUTHORIZATION_URL)
    print(
        "I will try to start a browser to visit the following Mastodon page "
        "if a browser will not start, copy the URL to your browser "
        "and retrieve the pincode to be used "
        "in the next step to obtaining an Authentication Token: \n"
        f"\n\t{url}\n"
    )
    webbrowser.open(url)

    print("\nGenerating and signing request for an access token...\n")

    resp = input("Enter the full callback URL after authorization: ")

    token = oauth_client.fetch_token(
        TOKEN_URL,
        authorization_response=resp,
        client_secret=client_secret,
    )

    print(token)

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

    print(f"\nYour access token is: {token['access_token']}")

    return token['access_token']


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="Estimate gender distribution of "
        "Mastodon following accounts, followers and"
        "your timeline"
    )
    p.add_argument("user_id", nargs=1)
    p.add_argument(
        "--self", help="perform gender analysis on user_id itself", action="store_true"
    )
    p.add_argument("--dry-run", help="fake results", action="store_true")
    args = p.parse_args()
    [user_id] = args.user_id

    client_id = os.environ.get("CLIENT_ID") or input("Enter your client id: ") # TODO: check client key/id

    client_secret = os.environ.get("CLIENT_SECRET") or input(
        "Enter your client secret: "
    )

    instance_name = os.environ.get("INSTANCE_NAME") or input(
        "Enter your instance name: "
    )

    if args.dry_run:
        tok = None
    else:
        tok = get_access_token(client_id, client_secret, instance_name)

    if args.self:
        if args.dry_run:
            g, declared = "male", True
        else:
            api = get_mastodon_api(client_id, client_secret, tok, instance_name)
            g, declared = analyze_self(api)

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
        following, followers, timeline = dry_run_analysis()
    else:
        api = get_mastodon_api(client_id, client_secret, tok, instance_name)
        following = analyze_following(user_id, None, api, cache)
        followers = analyze_followers(user_id, api, cache)
        timeline = analyze_timeline(user_id, None, api, cache)
        mytimeline = analyze_my_timeline(user_id, api, cache)
        boosts = mytimeline.get("boosts")
        replies = mytimeline.get("replies")
        mentions = mytimeline.get("mentions")

    duration = time.time() - start

    for user_type, an in [
        ("following", following),
        ("followers", followers),
        ("timeline", timeline),
        ("boosts", boosts),
        ("replies", replies),
        ("mentions", mentions),
    ]:
        nb, men, women, andy = an.nonbinary.n, an.male.n, an.female.n, an.andy.n

        print(
            "{:>25s}\t{:>10.2f}%\t{:10.2f}%\t{:10.2f}%".format(
                user_type, an.pct("nonbinary"), an.pct("male"), an.pct("female")
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

    print("")
    print(
        "Analysis took {:.2f} seconds, cache hit ratio {}%".format(
            duration, cache.hit_percentage
        )
    )
