Piece of code to modify in the mms_parser.py, because we can now have three files simultaneously.

```
self.path = Path("/none")
        self.path = {
            'main': None,
            'dom' : None,
            'ndom': None,
        }
```
