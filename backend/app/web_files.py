"""僅供應建置完成的網站檔案，不讓入口變成任意檔案下載。"""
import mimetypes
from pathlib import Path, PurePosixPath


def website_asset(root: Path, relative: str, access_code: str):
    root = root.resolve()
    relative = relative or 'index.html'
    parts = PurePosixPath(relative).parts
    if ('\\' in relative or relative.startswith('/') or not parts or
            any(part.startswith('.') for part in parts)):
        raise ValueError('Invalid website path')
    if relative not in {'index.html', 'favicon.svg'}:
        if parts[0] not in {'assets', 'licenses'}:
            raise ValueError('Not a website asset')
        if Path(relative).suffix.lower() not in {'.js', '.mjs', '.css', '.woff2', '.png', '.svg', '.txt'}:
            raise ValueError('Unsupported website asset')
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Website path escaped build directory')
    data = path.read_bytes()
    if len(data) > 8 * 1024 * 1024:
        raise ValueError('Website asset too large')
    if relative == 'index.html':
        html = data.decode('utf-8')
        html = html.replace('</head>',
                            f'<meta name="youluan-api-path" content="/{access_code}"></head>')
        data = html.encode('utf-8')
    content_type = 'text/javascript' if path.suffix in {'.js', '.mjs'} else mimetypes.guess_type(path.name)[0]
    return data, content_type or 'application/octet-stream'
