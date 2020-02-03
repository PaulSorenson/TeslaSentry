# Tesla Sentry Video

Stack all camera views into a single video for simpler review.

![snapshot](images/2020-01-31-12-06-38_st4_sp8_q30.jpg)

[feel free to use my referral code](https://ts.la/helen94378)

# Examples

## make stacked versions of all sentry events

With these settings the output video is usually less than 100 kB.

```
$ cd SentryEvents
$ sentry_stack.py --scale 4 --speed 8 --quality 30
```

Otherwise you can use `--sentry-dir` to tell `sentry_stack` where to find the sentry videos.

## show help

```
$ sentry_stack.py --help
usage: sentry_stack.py [-h] [--sentry-dir SENTRY_DIR] [--speed SPEED]
                       [--scale SCALE] [--quality QUALITY] [--list-dir]

optional arguments:
  -h, --help            show this help message and exit
  --sentry-dir SENTRY_DIR
                        Top level Sentry dir (./)
  --speed SPEED         int speed multiplier (1)
  --scale SCALE         scale down multiplier (4)
  --quality QUALITY     encode quality (23)
  --list-dir            list sub directories which correspond to Tesla sentry
                        events.
```

