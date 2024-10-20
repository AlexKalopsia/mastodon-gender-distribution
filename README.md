Gender Distribution of Mastodon Friends and Followers
====================================================

> [!WARNING]  
> The work is not done yet, so the tool is not currently working.

All the work was originally done by ajdavis on ajdavis/proporti.onl, which was calculating 
gender distribution on Twitter, before the free API got shut down. 
I am merely adapting it to work on Mastodon. 

This tool guesses the gender of your friends and followers by looking in
their Mastodon bios for pronoun announcements like "she/her", or else guessing
based on first name.

Read the original author's article **["72% Of The People I Follow On Twitter Are
Men."](https://emptysqua.re/blog/gender-of-twitter-users-i-follow/)**

Install
-------

This script requires Python 3.8, and the packages listed in `requirements.txt`.

```
python3 -m pip install -r requirements.txt
```

Command-line Use
----------------

Pass a Mastodon username to analyze the user's friends and followers:

```
python3 analyze.py jessejiryudavis
```

Test
----

From the repository root directory:

```
python3 -m unittest discover -v
```

Website
-------

Start a Flask server for testing:

```
CONSUMER_KEY=foo CONSUMER_SECRET=bar COOKIE_SECRET=baz python3 server.py 8000
```
