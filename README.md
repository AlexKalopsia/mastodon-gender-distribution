Gender Distribution of Mastodon Connections and Followers
====================================================

> [!WARNING]  
> The original Twitter tool was done by ajdavis on [ajdavis/proporti.onl](https://github.com/ajdavis/proporti.onl),
> before the free API got shut down.\
> I adapted it to work with Mastodon. 

This tool guesses the gender of your following account and followers by looking in
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

Pass a Mastodon user handle to analyze the accounts the user follows and their followers.\
It supports formats such as `alexkalopsia`, `@alexkalopsia`, `@alexkalopsia@mastodon.social` and `alexkalopsia@mastodon.social`:

```
python3 analyze.py alexkalopsia
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

Linux
```
CLIENT_KEY=foo CLIENT_SECRET=bar COOKIE_SECRET=baz INSTANCE=mastodon.social python3 server.py 8000
```

Windows
```
$env:CLIENT_KEY="foo"; $env:CLIENT_SECRET="bar"; $env:COOKIE_SECRET="baz"; $env:INSTANCE="mastodon.social"; py 
server.py 8000
```
