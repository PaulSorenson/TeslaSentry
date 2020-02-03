#!/usr/bin/env python3

import logging
import re
import subprocess as sp
from argparse import ArgumentParser, Namespace
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Tuple

log = logging.getLogger()
logging.basicConfig()
log.setLevel(logging.INFO)


re_sentry_dir = re.compile(
    r"(?P<year>)\d{4}}-(?P<month>\d{2})-(?P<day>\d{2})_"
    r"(?P<hour>\d{2})-(?P<min>\d{2})-(?P<sec>\d{2})"
)

# view is "front|back|left_repeater|right_repeater"
re_vid = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})_"
    r"(?P<hour>\d{2})-(?P<min>\d{2})-(?P<sec>\d{2})-(?P<view>.*)\.mp4"
)


@dataclass
class SentryEvent:
    "Collection of 4 videos for each time stamp."
    # top level path to all senty events, could be relative
    sentry_dir: Path
    # individual date dir containing one or more sentry events
    date_dir: Path
    # datetime representation of the video paths.
    sentry_event_id: datetime
    # should have exactly 4 paths front|back|left_repeater|right_repeater
    video_paths: List[Path]

    @property
    def event_dir(self) -> Path:
        return self.sentry_dir / self.date_dir

    def get_view(self, view: str) -> Path:
        return [p for p in self.video_paths if str(p).find(view) != -1][0]

    @property
    def front(self) -> Path:
        return self.event_dir / self.get_view("front")

    @property
    def back(self) -> Path:
        return self.event_dir / self.get_view("back")

    @property
    def left(self) -> Path:
        return self.event_dir / self.get_view("left_repeater")

    @property
    def right(self) -> Path:
        return self.event_dir / self.get_view("right_repeater")

    @property
    def views(self):
        return [self.front, self.back, self.left, self.right]

    def output_path(self, scale: int, speed: int, quality: int) -> Path:
        return (
            self.event_dir / f"{self.sentry_event_id.strftime('%Y-%m-%d-%H-%M-%S')}"
            f"_st{scale}_sp{speed}_q{quality}"
            ".mp4"
        )


def get_args() -> Tuple[Namespace, List]:
    ap = ArgumentParser(
        description="Stack your Tesla model3 sentry videos into a single output. "
        "WARNING: any arguments not explicitly recognized are considered "
        "global options which are added to the command line immediately after ffmpeg. "
        "Consider using the --dry-run argument and also inspect "
        "the logs for 'global options', if this list is not empty "
        "then proceed with caution."
    )

    ap.add_argument(
        "--sentry-dir",
        type=Path,
        default="./",
        help="Top level Sentry dir (%(default)s)",
    )
    ap.add_argument(
        "--speed", type=int, default=1, help="int speed multiplier (%(default)s)."
    )
    ap.add_argument(
        "--scale",
        type=int,
        default=4,
        help="scale down multiplier (%(default)s). "
        "Eg set to 2 for half the width/height.",
    )
    ap.add_argument(
        "--quality",
        type=int,
        default=23,
        help="encode quality (%(default)s). "
        "Increase this to reduce quality and filesize.",
    )
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="Silently overwrite output file, otherwise skip.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print commands but do not execute. "
        "Note this is for information only, you may need to tweak the escaping.",
    )
    ap.add_argument(
        "--list-dir",
        action="store_true",
        help="list sub directories which correspond to Tesla sentry events.",
    )

    opt = ap.parse_known_args()
    return opt


def events_dir_iter(sentry_dir: Path) -> Generator[Path, None, None]:
    "Iterate over the sub directories in SentryDir"
    yield from [x for x in sentry_dir.iterdir() if x.is_dir()]


def event_groups(events_dir: Path,) -> defaultdict:
    "Iterate over videos and return them in time synced groups of 4 vids"
    grps: defaultdict = defaultdict(list)
    for vid_path in sorted(events_dir.iterdir()):
        vid = vid_path.parts[-1]
        m = re_vid.match(str(vid))
        if m:
            grp_id = datetime(*[int(c) for c in m.groups()[:-1]])
            grps[grp_id].append(vid)
    return grps


def compose_stack_cmd(
    event: SentryEvent,
    scale: int = 4,
    speed: int = 1,
    quality: int = 23,
    global_opts: List[str] = None,
) -> List[str]:
    """
    Compose ffmpeg command to process `SentryEvent` and return it in list
    form for subprocess run.

    :param event: SentryEvent object.
    :param scale: divisor for output video dimensions. Note since there
    are 4 videos in the output, using scale=4 (the default) will result
    in output size the same as one of the source videos.
    :param speed: speed up factor.
    :param quality: increase this to reduce quality and output file size.
    :param global_opts: any strings provided here are added immediately
    after the command.
    """

    views = ["front", "back", "left", "right"]

    cmd = ["ffmpeg"]

    if global_opts:
        cmd.extend(global_opts)

    for v in views:
        try:
            cmd.extend(["-i", str(event.event_dir / event.get_view(v))])
        except IndexError:
            # hack for pre 10.0 sw with no back video
            cmd.extend(["-i", str(event.event_dir / event.get_view("front"))])
    cmd.extend(["-an", "-filter_complex"])
    filter = []
    for i, v in enumerate(views):
        filter.extend([f"[{i}:v]", f"scale=iw/{scale}:ih/{scale}", f"[{v}];"])
    filter.extend(["[front][back]", "hstack", "[long];"])
    filter.extend(["[right][left]", "hstack", "[lat];"])
    filter.extend(["[long][lat]", "vstack", "[all];"])
    filter.extend(["[all]", f"setpts={1/speed}*PTS", "[res]"])
    filter_string = "".join(filter)
    cmd.append(f"{filter_string}")
    cmd.extend(["-c:v", "libx264", "-crf", f"{quality}"])
    output_path = event.output_path(scale, speed, quality)
    cmd.extend(["-map", "[res]", str(output_path)])
    return cmd


def main():
    opt, global_opts = get_args()
    log.info(f"{opt} global options: {global_opts}")

    if opt.overwrite:
        # don't need to explicitly set -n for the converse case
        # because the check is done before the ffmpeg comand is run.
        global_opts.append("-y")

    if opt.list_dir:
        print(list(events_dir_iter(opt.sentry_dir)))

    events = [
        SentryEvent(
            sentry_dir=opt.sentry_dir,
            date_dir=sentry_date,
            sentry_event_id=date,
            video_paths=video_paths,
        )
        for sentry_date in events_dir_iter(opt.sentry_dir)
        for date, video_paths in event_groups(sentry_date).items()
    ]
    log.info(f"found {len(events)} events")

    for event in events:
        if not opt.overwrite:
            op = event.output_path(
                scale=opt.scale, speed=opt.speed, quality=opt.quality
            )
            if op.exists():
                log.info(f"output: '{op}' exists, skipping. See --overwrite.")
                continue
        print(event)
        print(event.front)
        cmd = compose_stack_cmd(
            event,
            scale=opt.scale,
            speed=opt.speed,
            quality=opt.quality,
            global_opts=global_opts,
        )
        print(" ".join(cmd))
        if not opt.dry_run:
            sp.run(cmd)


if __name__ == "__main__":
    main()
