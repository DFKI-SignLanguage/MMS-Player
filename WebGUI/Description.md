# MMS-Player Web remote interface

This is the description of the software interface to use the MMS-Player through a web browser.

It is based on a client/server architecture where the server has access to the Dictionary of signs and to the MMS-Player, and the client exposes an interface to edit an MMS instance and see the animated result.

## Server

When started, the server must be given the following locations:

* The folder of the Dictionary of signs.
* The folder containing the MMS-Player. By default, this is the parent folder.
* A project folder, where MMS instances, renders, and caches are stored. It is created if it doesn't exist.
* The Blender executable used to run the MMS-Player.

The server is responsible for generating the HTML code of the interface, as well as invoking the local instance of the MMS-Player in order to generate the MP4 videos that are then shown in the web interface.

To save rendering time, the server can also invoke the MMS-Player to export only the animation data (a JSON file), without rendering any video. The JSON animation data is sent to the client, which plays it in real time on a 3D character.


## Client GUI

The web interface is divided into three sections, arranged horizontally.

### Dictionary preview

On the left side, we have the dictionary exploration panel.

It lists all the signs present in the selected dictionary.
Users can filter the visible signs by typing part of the name.
At the bottom, it is possible to see a preview of the selected sign, played in real time on the 3D character (the same used for the full sentence preview). Videos are rendered only for full sentences.

### MMS editing

In the central part, we have an MMS editor, showing an MMS instance as a table.
The user can perform several operations:

* Insert and remove rows.
* Edit the content of the cells.
* Change the order of the rows.

The columns of the MMS are divided into sections:

* The first section is the sign sequence, including the columns `maingloss`, `domarm`, and `ndomarm`.
  * While typing the name of a sign in a cell, the dictionary panel on the left lists the candidate signs, filtered by the typed characters.
  * Clicking a sign in this list shows a real-time 3D preview of the single sign from the dictionary.
  * Double-clicking a sign inserts it into the edited cell.
* The second section is the timing information: `framestart`, `frameend`, `transition`, and `duration` columns.
  * A checkbox lets the user choose between absolute timing (`framestart`/`frameend`) and relative timing (`transition`/`duration`).
* The third section is the set of inflection parameters.
  * Inflection parameters are also divided into subsections, one for each body part: Torso, Head, Shoulders, Dominant hand, and Non-dominant hand. Each body part can be hidden.
  * The x/y/z components of an inflection parameter are grouped, and they can optionally be shown in separate columns or collapsed into a single cell.

Below the MMS table, there is a timeline showing a preview of the timing information.
The timeline flows horizontally to the right, and the time range of the selected MMS row is highlighted on the timeline.


### Sign language animation view

On the right side lies the generated sign language utterance, shown either as real-time 3D preview or as rendered video.
A selection tab switches between the two views.

* A button named "Preview 3D" invokes the MMS-Player on the server to compute only the animation data. The data is played back in real time on the 3D character, loaded in GLB format (exported from the template Blender scene of the MMS-Player) and shown with the Three.js library. The user can orbit and zoom the camera.
* A button named "Render video" invokes the MMS-Player on the server to render the final video, shown in the video view. Users render the video only once they are satisfied with the 3D preview.

While the animation or the video is generated, the user is informed of the progress of the task.
Previous renders are listed below the views. Their animation data is also exported, so they can be seen in the 3D view too.


## Tech info

This project is a standalone project which doesn't depend on the parent folder.
It contains its own list of requirements.

At the first start, a local file `server_options.local.json` is created with default options.
Edit it as needed and restart the server to apply the changes.
