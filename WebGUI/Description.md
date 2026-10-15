# MMS-Player Web remote interface

This is the description of the software interface to use the MMS player through web browser.

It is based on a client/server architecture where the server has access to Dictionary of signs and to the MMS player, and the client exposes an interface to edit an MMS instance and see the animated result.

## Server

At start the server must be booked by specifying three locations:

* the folder with the dictionary of science.
* the folder containing the MMS player by default. This is the parent folder.
*  A project folder, where instances of the MMS are stored.

The server is responsible of generating the HTML code of the interface, as well as an invoking the local instance of the MMS-Player in order to generate the animation data or the MP4 videos that then showed on the web interface.


## Client GUI

The web interface is divided in two sections, arranged the horizontally.
On the left side, we have an MMS editor. It means that it shows an MMS instance as a table and the user can perform several operations:

* Insert and remove rows.
* Edit the content of the cells.
* Change the order of the rows.

 The columns of the MMS are divided in sections:

* The first section is the sign sequence, including the columns maingloss and domarm and ndomarm.
  *  While typing the name of a sign in a cell, a separate frame shows the list of all possible candidate signs, filtered by the typed characters.
  * Selecting a sign from this list, shows a preview video of the single sign from the dictionary.
  *    Double clicking on the gloss inserts it in the edited cell.
* The second section is the timing information: framestart, frameend, transition, and duration columns.
  *  A checkbook allows to specify if we are using the absolute timing or the relative timing.
* The third section is the set of inflection parameters.
  * Inflection parameters are also divided in subsections, one for each of the specific body parts.
  * The several x/y/z components of an inflection parameter are gouped and they can be optionally be visible or hidden.

Below the MMS table, editor, there is a timeline showing up preview of the timing information.
The timeline flows horizontally to the right and the MMS row time range is highlighted on the timeline.

A button named "Generate" invokes the MMS player on the server and shows the resulting video on the right side of the interface.
While the video is generated, the user is informed of the progress of the task.

## Tech info

This project is a standalone project which doesn't depend from the parent folder.
It contains its own list of requirements.
