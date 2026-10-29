"""依chunk3.1契約取得章節欄位；不跨目錄匯入Code的同名模組。"""


def section_fields(title):
    root = title['heading']
    paths = []

    def visit(node, ancestors):
        path = ancestors+[node['text']]
        if not node['children']:
            paths.append(' > '.join(path))
        for child in node['children']:
            visit(child, path)

    if root and title['main_title'] != '會計師查核報告':
        for child in root['children']:
            visit(child, [])
    return {'main_section': title['main_title'],
            'sub_section': root['text'] if root else '', 'note_title': paths}
