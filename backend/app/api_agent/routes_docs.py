"""Routes de documentation OpenAPI : /openapi.json et /docs."""

from flask import jsonify, make_response

from app.api_agent import app
from app.openapi import build_spec

_SWAGGER_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Chatbot API – Swagger UI</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
  SwaggerUIBundle({
    url: "/openapi.json",
    dom_id: '#swagger-ui',
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
    layout: "BaseLayout",
    deepLinking: true
  });
</script>
</body>
</html>"""


@app.route("/openapi.json", methods=["GET"])
def openapi_spec():
    return jsonify(build_spec())


@app.route("/docs/", methods=["GET"])
@app.route("/docs", methods=["GET"])
def swagger_ui():
    r = make_response(_SWAGGER_HTML)
    r.headers["Content-Type"] = "text/html"
    return r
