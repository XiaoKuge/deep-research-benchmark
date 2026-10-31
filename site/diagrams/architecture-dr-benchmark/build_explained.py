"""给 Archify 生成的架构图加上节点说明，另存为讲解版。

用法：python3 -I build_explained.py
原图 benchmark-architecture.html 保持原样（它的检查回执仍然有效），
讲解版 benchmark-architecture-explained.html 由原图加上 node-notes.json 里的说明生成。
改了 candidate.json 先用 Archify 重新生成原图，再运行本脚本；只改说明文字时直接运行本脚本。

讲解版做四件事：
1. 点击节点弹出的卡片只留标题和关闭按钮，下面写"这是什么""做什么用"，附规则手册里对应的一节和"看实例"；
2. 卡片里的类型、编号、上下游计数、复制链接、关系列表不再显示；
3. 工具栏里要人猜用法的路径、透镜、雷达、风格切换不再显示；
4. 网址带 ?embedded=1 时（《一道题走完全程》页面嵌入用），只显示图：不显示标题栏、工具栏、下方卡片和节点卡；
   点节点时通知外层页面，外层页面滚到对应的一站。
本脚本依赖 Archify 3.2 生成页面里的元素编号（data-node-id、focus-chip 等），升级 Archify 后要重新检查。
"""
import html
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "benchmark-architecture.html")
OUT = os.path.join(HERE, "benchmark-architecture-explained.html")
NOTES = os.path.join(HERE, "node-notes.json")
RULES = "../../../notes/rules.html"
WALK = "../../walkthrough.html"

CSS = """
<script>if (/[?&]embedded=1(&|$)/.test(location.search)) document.documentElement.classList.add('nn-embedded');</script>
<style id="node-notes-style">
  html.nn-embedded .toolbar, html.nn-embedded .header, html.nn-embedded #reader-rail,
  html.nn-embedded #focus-chip { display: none !important; }
  html.nn-embedded body { margin: 0 !important; padding: 0 !important; }
  html.nn-embedded .container { margin: 0 !important; padding: 8px !important; max-width: none !important; }
  html.nn-embedded [data-node-id] { cursor: pointer; transition: opacity 500ms cubic-bezier(0.22, 1, 0.36, 1); }
  html.nn-station [data-node-id] { opacity: .28; }
  html.nn-station [data-node-id].nn-current { opacity: 1; filter: drop-shadow(0 0 8px rgba(47, 91, 211, .65)); }
  .relationship-lens-eyebrow, #focus-detail, #focus-passport-meta, #focus-evidence, #focus-summary,
  #focus-reach, #btn-focus-copy, #btn-focus-relations, #relationship-lens-list,
  #btn-route-probe, #btn-semantic-lens, #btn-overview-map, #btn-preset, #preset-menu { display: none !important; }
  #focus-chip { width: min(420px, calc(100vw - 32px)) !important; max-width: min(420px, calc(100vw - 32px)) !important; }
  .node-note { margin-top: 8px; max-height: min(52vh, 420px); overflow-y: auto; }
  .node-note h4 { margin: 12px 0 4px; font-size: 12px; line-height: 16px; font-weight: 600; opacity: .7; }
  .node-note h4:first-child { margin-top: 0; }
  .node-note p { margin: 0; font-size: 14px; line-height: 22px; font-weight: 400; white-space: normal; }
  .node-note .rule { margin-top: 12px; font-size: 13px; line-height: 20px; }
  .node-note a { color: inherit; text-decoration: underline; text-underline-offset: 3px; }
</style>
"""

JS = """
<script id="node-notes-script">
(function () {
  var NOTES = __NOTES__;
  var RULES = __RULES__;
  var WALK = __WALK__;
  var embedded = document.documentElement.classList.contains('nn-embedded');
  if (embedded) {
    // 嵌入时不用 Archify 的聚焦（它会放大），改为标亮当前一站，始终看得见全图。
    // 初始的一站写在网址的 #station=节点 里；之后由外层页面发消息切换（本机文件改网址会整页重新加载）
    var mark = function (id) {
      document.documentElement.classList.toggle('nn-station', !!id);
      document.querySelectorAll('[data-node-id]').forEach(function (el) {
        el.classList.toggle('nn-current', el.getAttribute('data-node-id') === id);
      });
    };
    var m = /[#&]station=([A-Za-z][A-Za-z0-9_-]*)/.exec(location.hash);
    mark(m ? m[1] : null);
    window.addEventListener('message', function (e) {
      var d = e.data;
      if (d && d.type === 'node-notes-station' && (d.id === null || NOTES[d.id])) mark(d.id);
    });
    // 点节点：不让 Archify 聚焦放大；把节点名和说明交给外层页面，由外层页面按正常字号显示节点卡
    var tell = function (el) {
      var nid = el.getAttribute('data-node-id');
      if (window.parent === window || !NOTES[nid]) return;
      var r = el.getBoundingClientRect();
      var x = (r.left + r.width / 2) / Math.max(1, document.documentElement.clientWidth); // 节点在图上的左右位置，0 到 1
      window.parent.postMessage({ type: 'node-notes-click', id: nid, label: el.getAttribute('data-node-label'), note: NOTES[nid], x: x }, '*');
    };
    var stop = function (e) { e.stopPropagation(); e.preventDefault(); };
    document.querySelectorAll('[data-node-id]').forEach(function (el) {
      ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'dblclick'].forEach(function (t) { el.addEventListener(t, stop, true); });
      el.addEventListener('click', function (e) { stop(e); tell(el); }, true);
      el.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { stop(e); tell(el); } }, true);
    });
  }
  var copy = document.querySelector('#focus-chip .relationship-lens-copy');
  var title = document.getElementById('relationship-lens-title');
  if (!copy || !title) return;
  var box = document.createElement('div');
  box.className = 'node-note';
  box.id = 'node-note';
  title.insertAdjacentElement('afterend', box);

  function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function current() {
    var el = document.querySelector('[data-node-id][aria-pressed="true"]');
    return el ? el.getAttribute('data-node-id') : null;
  }
  var shown = null;
  function update() {
    var id = current();
    if (id === shown) return;
    shown = id;
    var n = id && NOTES[id];
    if (!n) { box.innerHTML = ''; return; }
    box.innerHTML =
      '<h4>这是什么</h4><p>' + esc(n.what) + '</p>' +
      '<h4>做什么用</h4><p>' + esc(n.use) + '</p>' +
      (n.rule ? '<p class="rule">详见规则手册<a href="' + RULES + '#' + esc(n.rule[1]) + '" target="_blank" rel="noopener">' + esc(n.rule[0]) + '</a></p>' : '') +
      '<p class="rule"><a href="' + WALK + '#step-' + esc(id) + '" target="_top">看实例：淡水湖这道题走到这一站</a></p>';
  }
  var mo = new MutationObserver(update);
  document.querySelectorAll('[data-node-id]').forEach(function (el) { mo.observe(el, { attributes: true, attributeFilter: ['aria-pressed'] }); });
  mo.observe(title, { childList: true, subtree: true, characterData: true });
  window.addEventListener('hashchange', function () { setTimeout(update, 0); });
  update();
})();
</script>
"""


def main():
    with open(SRC, encoding="utf-8") as f:
        page = f.read()
    with open(NOTES, encoding="utf-8") as f:
        notes = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    missing = [i for i in ("qcard", "agents", "runner", "reports", "verify", "pool", "depthmap",
                           "ratings", "scorer", "ranks", "package") if i not in notes]
    assert not missing, missing
    for nid in notes:
        assert f'data-node-id="{nid}"' in page, f"图里没有节点 {nid}"
    for needle in ('id="focus-chip"', 'class="relationship-lens-copy"', 'id="relationship-lens-title"'):
        assert needle in page, f"Archify 页面结构变了：找不到 {needle}"
    assert page.count("</head>") == 1 and page.count("</body>") == 1
    js = JS.replace("__NOTES__", json.dumps(notes, ensure_ascii=False).replace("</", "<\\/"))
    js = js.replace("__RULES__", json.dumps(RULES)).replace("__WALK__", json.dumps(WALK))
    page = page.replace("</head>", CSS + "</head>", 1).replace("</body>", js + "</body>", 1)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, OUT)
    print("wrote", os.path.basename(OUT), "with", len(notes), "node notes")


if __name__ == "__main__":
    main()
