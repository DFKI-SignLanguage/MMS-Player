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


## Client GUI

The web interface is divided into three sections, arranged horizontally.

### Dictionary preview

On the left side, we have the dictionary exploration panel.

It lists all the signs present in the selected dictionary.
Users can filter the visible signs by typing part of the name.
At the bottom, it is possible to see a preview of the selected sign.

### MMS editing

In the central part, we have an MMS editor, showing an MMS instance as a table.
The user can perform several operations:

* Insert and remove rows.
* Edit the content of the cells.
* Change the order of the rows.

The columns of the MMS are divided into sections:

* The first section is the sign sequence, including the columns `maingloss`, `domarm`, and `ndomarm`.
  * While typing the name of a sign in a cell, the dictionary panel on the left lists the candidate signs, filtered by the typed characters.
  * Clicking a sign in this list shows a preview video of the single sign from the dictionary.
  * Double-clicking a sign inserts it into the edited cell.
* The second section is the timing information: `framestart`, `frameend`, `transition`, and `duration` columns.
  * A checkbox lets the user choose between absolute timing (`framestart`/`frameend`) and relative timing (`transition`/`duration`).
* The third section is the set of inflection parameters.
  * Inflection parameters are also divided into subsections, one for each body part: Torso, Head, Shoulders, Dominant hand, and Non-dominant hand. Each body part can be hidden.
  * The x/y/z components of an inflection parameter are grouped, and they can optionally be shown in separate columns or collapsed into a single cell.

Below the MMS table, there is a timeline showing a preview of the timing information.
The timeline flows horizontally to the right, and the time range of the selected MMS row is highlighted on the timeline.


### Sign language animation view

On the right side lies the video of the generated sign language utterance.

A button named "Generate" invokes the MMS-Player on the server and shows the resulting video on the right side of the interface.
While the video is generated, the user is informed of the progress of the task.
Previous renders are listed below the video.


## Tech info

This project is a standalone project which doesn't depend on the parent folder.
It contains its own list of requirements.

At the first start, a local file `server_options.local.json` is created with default options.
Edit it as needed and restart the server to apply the changes.
