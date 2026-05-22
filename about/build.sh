#!/usr/bin/env bash
# Rebuild about/index.html from about/AIWriters.jsx.
# Run this after editing AIWriters.jsx, then `git commit && git push`.
set -e
cd "$(dirname "$0")"
echo "Rebuilding index.html from AIWriters.jsx..."
cat > index.html <<'HTML_HEAD'
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>NSMT — Meet the AI Writers</title>
  <meta name="description" content="14 AI writers covering DC, Maryland, and Virginia sports. Built and bylined honestly. By NSMT.">
  <meta property="og:title" content="NSMT — Meet the AI Writers">
  <meta property="og:description" content="14 AI writers. 1 solo founder. $0/month. Full transparency.">
  <meta property="og:type" content="website">
  <script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <style>html,body{margin:0;padding:0;background:#0B0B0C;}</style>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel" data-presets="react">
    const { useEffect, useState } = React;
HTML_HEAD
sed -e '1d' -e 's/^export default //' AIWriters.jsx >> index.html
cat >> index.html <<'HTML_FOOT'
    ReactDOM.createRoot(document.getElementById('root')).render(<AIWriters />);
  </script>
</body>
</html>
HTML_FOOT
echo "Done. index.html is $(wc -l < index.html) lines / $(wc -c < index.html) bytes."
