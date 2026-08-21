#    MMS Player - procedural animation of Sign Language avatars
#    Copyright (C) 2024 German Research Center for Artificial Intelligence (DFKI)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

import argparse
import json
import sys

import requests


def main():
    parser = argparse.ArgumentParser(description="Call the MMS-Player server's /api/mms/animation endpoint.")
    parser.add_argument("server_address", help="Server address:port, e.g. localhost:5000")
    parser.add_argument("mms_file", help="Path to the input .mms file")
    parser.add_argument("animation_file", help="Path where the resulting animation JSON will be saved")
    args = parser.parse_args()

    url = f"http://{args.server_address}/api/mms/animation"

    with open(args.mms_file, "rb") as mms_stream:
        files = {"file": (args.mms_file, mms_stream)}
        print(f"Posting '{args.mms_file}' to {url} ...")
        response = requests.post(url, files=files)

    if not response.ok:
        print(f"Server returned an error: {response.status_code} {response.reason}", file=sys.stderr)
        print(response.text, file=sys.stderr)
        sys.exit(1)

    animation_json = response.json()

    with open(args.animation_file, "w") as out_stream:
        json.dump(animation_json, out_stream, indent=2)

    print(f"Animation saved to '{args.animation_file}'.")


if __name__ == "__main__":
    main()
