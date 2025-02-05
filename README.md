Gender Distribution of Mastodon Connections and Followers
====================================================

> [!NOTE]  
> The original tool was created by [ajdavis](https://github.com/ajdavis/proporti.onl) for Twitter,
> before the free API got shut down.\
> I have adapted the original project to work with Mastodon.

Mastodon Proportional guesses the gender of your followers and those you follow by looking in
their Mastodon profile names, bios, and extra fields for pronoun announcements like "she/her", or else guessing it
based on first name.

Read the original author's article **["72% Of The People I Follow On Twitter Are
Men."](https://emptysqua.re/blog/gender-of-twitter-users-i-follow/)**

Install
-------

This script requires Python 3.8, and the packages listed in `requirements.txt`.

```python
py -m pip install -r requirements.txt
```

Deploy
-------

The repo contains an example `app_render.wsgi` config useful when deploying to [PythonAnywhere](https://www.pythonanywhere.com/).

If you want to deploy to [Railway](https://railway.com/), make sure you set the `COOKIE_SECRET` and `DEPLOY_URL` env variables.

Command-line Use
----------------

Pass a Mastodon user handle to analyze the accounts the user follows and their followers.\
It supports formats such as `alexkalopsia`, `@alexkalopsia`, `@alexkalopsia@mastodon.social` and `alexkalopsia@mastodon.social`:

```python
py analyze.py alexkalopsia@mastodon.social
```

Test
----

From the repository root directory:

```python
py -m unittest discover -v
```

Local server
-------

Start a Flask server for testing:

Linux

```bash
COOKIE_SECRET=foo python3 server.py 8000
```

Windows

```bash
$env:COOKIE_SECRET="foo"; py server.py 8000
```
