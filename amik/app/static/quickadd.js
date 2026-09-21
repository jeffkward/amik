/* Quick add to the board's Inbox, from anywhere in the face.
 *
 * base.html includes this on every page, but only when the instance has a
 * board — so on a ported install neither the dialog nor this file exists.
 *
 * Cmd/Ctrl+K opens it with the box focused; Enter commits; Escape closes.
 * The /amik page reuses the same dialog for its + button rather than
 * keeping a second copy, and amik.js calls the entry point below.
 */
(function () {
  var dlg = document.getElementById('aknew');
  if (!dlg) return;                       /* no board on this instance */
  var box = document.getElementById('aknew-title');
  var go = document.getElementById('aknew-go');
  var done = document.getElementById('aknew-done');
  var row = dlg.querySelector('.akquickrow');
  var busy = false;

  function open() {
    box.value = '';
    done.hidden = true;
    row.hidden = false;
    if (!dlg.open) dlg.showModal();
    box.focus();
  }
  /* The one entry point. The + on Inbox calls this, so the button and the
     chord cannot drift into two behaviours. */
  window.amikQuickAdd = open;

  function create() {
    if (busy) return;
    var title = box.value;
    if (!title || !title.trim()) { box.focus(); return; }
    var body = new URLSearchParams();
    body.set('title', title.trim());
    /* No fingerprint. Most pages never rendered the board and have none to
       quote; the route reads "" as "do not check", which is sound for this
       verb because a create appends at the top of inbox off a fresh read
       and has no prior state to clobber. */
    busy = true;
    fetch((window.akBase ? window.akBase() : '') + '/cards',
           {method: 'POST', body: body})
      .then(function (r) {
        if (!r.ok) throw r.status;
        return r.json();
      })
      .then(function () {
        /* A page SHOWING the board is now stale, so it reloads and the new
           card appears where it landed. Anywhere else there is nothing to
           repaint, so the dialog says so for a beat instead — otherwise a
           successful add looks identical to a dropped keystroke. */
        if (document.querySelector('.akboard')) {
          window.location.reload();
          return;
        }
        row.hidden = true;
        done.hidden = false;
        setTimeout(function () { dlg.close(); busy = false; }, 900);
      })
      .catch(function () {
        busy = false;
        /* The board's own banner lives on /amik only, so the refusal is
           reported in the box the typing is already in. The text is not
           lost: the dialog stays open with it. */
        box.setAttribute('aria-invalid', 'true');
        done.hidden = false;
        done.textContent = 'That could not be saved. Try again?';
      });
  }

  go.addEventListener('click', create);
  box.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); create(); }
  });

  /* Cmd/Ctrl+K anywhere. preventDefault is required rather than tidy: the
     browser owns this chord (Chrome puts the omnibox into search mode) and
     would take the keystroke first.
     
     It stands down wherever a keystroke already means something — any open
     dialog, any field, and anything inside a CodeMirror editor, where
     Cmd+K is the editor's own. A global chord that eats typing is worse
     than no global chord. */
  function typing(el) {
    if (!el) return false;
    if (el.isContentEditable) return true;
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return true;
    return !!el.closest('.cm-editor');
  }
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'k' && e.key !== 'K') return;
    if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey) return;
    if (document.querySelector('dialog[open]')) return;
    if (typing(document.activeElement)) return;
    e.preventDefault();
    open();
  });
})();
