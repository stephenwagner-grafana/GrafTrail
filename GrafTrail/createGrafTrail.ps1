pyinstaller --noconsole --onefile `
  --name GrafTrail `
  --icon .\GrafTrail\Resources\graftrail.ico `
  --add-data ".\GrafTrail\Resources\graftrail.ico;Resources" `
  .\GrafTrail\app.py
