/* The /amik board: a card opens to be read, and drag reorders.

   The modal has two modes. It opens in VIEW — chips and rendered prose —
   because a card is read far more often than it is written, and the
   pencil swaps in the form: the fields own the item's own content, title,
   where it sits on the planning ladder, its area, and nothing else.
   Status and rank belong to the drag, because two writers for one field
   is how a board and its file drift apart.

   The body field is a plain <textarea>. A rich editor renders into a
   contenteditable surface, which iOS treats as no field at all —
   autocorrect, autocapitalisation and the predictive strip are all off
   there. This board gets written from a phone. */

/* Where Amik is mounted. "" standing alone, "/amik" inside a host — read
   from the board element so one server-rendered attribute moves every URL
   this file builds. */
window.akBase = function () {
  var board = document.querySelector('.akboard');
  return (board && board.dataset.base) || '';
};

/* One write helper for every change on this page. Real verbs, because
   every write here is a fetch and not a form: a form cannot send PATCH or
   DELETE, which is the only reason anyone reaches for _method.

   It surfaces the SERVER'S reason: "the board changed on disk" is one
   cause among several, and claiming it for a rejected rung or an empty
   title sends you looking in the wrong place. */
/* Where a refusal is shown. Two places, painted together, because the
   page's banner and the card modal are in different layers and only one
   of them is ever on screen: a <dialog> shown with showModal() sits in
   the top layer above the page and dims it with a backdrop, so a write
   refused from inside an open card reported only on the page is a
   message nobody can read. Both carry the same sentence; whichever is
   visible is the one that gets read. */
window.akBanners = function () {
  return [[document.getElementById('akstale'),
           document.getElementById('akmsg')],
          [document.getElementById('akdlgmsg'),
           document.getElementById('akdlgwhy')]];
};

window.akQuiet = function () {
  window.akBanners().forEach(function (pair) {
    if (pair[0]) pair[0].hidden = true;
  });
};

/* One card's data block, fetched. Returns a detached element, so the
   caller decides where it goes and nothing is inserted into the page --
   the modal reads from it and never shows it. */
window.akCard = function (id) {
  return fetch(window.akBase() + '/cards/' + encodeURIComponent(id))
    .then(function (r) {
      if (!r.ok) { throw r.status; }
      return r.text();
    })
    .then(function (html) {
      var holder = document.createElement('div');
      holder.innerHTML = html;
      var el = holder.querySelector('.akdata');
      if (!el) { throw 0; }
      return el;
    });
};

window.akSend = function (method, path, body) {
  return fetch(window.akBase() + path,
               {method: method, body: body}).then(function (r) {
    if (r.ok) {
      window.akQuiet();
      return r.json();
    }
    return r.text().then(function (text) {
      var why = '';
      try { why = (JSON.parse(text).detail || '') + ''; } catch (e) { why = ''; }
      var said = r.status === 409
        ? 'The board changed on disk since this page loaded, so nothing '
          + 'was saved. Reload to pick up the new version.'
        : (why || ('That write was refused (' + r.status + ').'));
      window.akBanners().forEach(function (pair) {
        if (pair[1]) pair[1].textContent = said;
        if (pair[0]) pair[0].hidden = false;
      });
      throw r.status;
    });
  });
};

(function () {
  var dlg = document.getElementById('akdlg');
  if (!dlg) return;
  var board = document.querySelector('.akboard');
  var host = document.getElementById('akeditor');
  var titleEl = document.getElementById('aktitle');
  var idEl = document.getElementById('akidtext');
  var dateSlot = document.getElementById('akdateslot');
  var protoLink = document.getElementById('akf-protolink');
  var branchName = document.getElementById('akf-branchname');
  var outcome = document.getElementById('akoutcome');
  var outcomeBody = document.getElementById('akoutbody');
  var saveBtn = document.getElementById('aksave');
  var qList = document.getElementById('akqlist');
  var tabs = document.getElementById('aktabs');
  var details = document.getElementById('akdetails');
  var viewPane = document.getElementById('akview');
  var viewChips = document.getElementById('akviewchips');
  var viewBody = document.getElementById('akviewbody');
  var form = document.getElementById('akform');
  var editBtn = document.getElementById('akedit');
  var f = {
    title: document.getElementById('akf-title'),
    planning: document.getElementById('akf-planning'),
    status: document.getElementById('akf-status'),
    group: document.getElementById('akf-group'),
    newGroup: document.getElementById('akf-newgroup'),
    newGroupRow: document.getElementById('akf-newgroup-row'),
    halt: document.getElementById('akf-halt'),
    prototype: document.getElementById('akf-prototype')
  };
  var block = null, clean = null;
  /* The card's body as it was opened, and whether this card has been
     handed to the editor yet. ONE field is reused across cards, so
     reading it before that handover answers with whatever card was
     edited last. */
  var docText = '', editing = false;

  function bodyText() {
    return editing ? host.value : docText;
  }

  /* The Area the form MEANS: the select unless it is parked on "New
     area…", in which case the text box beside it is the answer. One
     reader, so snapshot/save/write-back cannot disagree about it. */
  function groupValue() {
    return f.group.value === '__new__'
      ? f.newGroup.value.trim() : f.group.value;
  }

  /* aria-pressed IS the state — one place, and the thing a screen reader
     reads. Reading it back rather than keeping a parallel variable is
     what stops the two disagreeing. */
  function pressed(el) { return el.getAttribute('aria-pressed') === 'true'; }
  function press(el, on) { el.setAttribute('aria-pressed', on ? 'true' : 'false'); }

  /* The columns a card is finished in. Nothing reads the handling
     toggles from here: the queue takes its gate from a halted card in
     `review` or in `ready`, a closed card is not going to be built on a
     branch, and the prototype sweep keys off the directory rather than
     the flag. */
  var CLOSED = ['done', 'abandoned'];

  /* Which toggles may still be moved, in one place — the halt rule used
     to be computed here and again in the click handler, which is two
     copies of one rule waiting to disagree.

     Disabled, never cleared: on a closed card these stop being levers
     and become the record of how the card was handled, and `⏸` still
     showing pressed is how a done card says it paused for a look before
     it landed. The planning rung IS cleared on a closed row because it
     says what is still OWED, which is a different kind of fact. */
  function paintHandling() {
    var closed = CLOSED.indexOf(f.status.value) >= 0;
    f.prototype.disabled = closed;
    /* A prototype forces the halt wherever the state is set, and that
       still holds on a card that is open. */
    f.halt.disabled = closed || pressed(f.prototype);
  }

  function snapshot() {
    /* The answer boxes are part of the form's state: typing in one has to
       enable Save the same way typing in the title does. Headings ride
       along with the values so that reordering the questions counts as a
       change rather than cancelling out. */
    var answers = [];
    qList.querySelectorAll('.akqbox').forEach(function (box) {
      answers.push([box.dataset.heading, box.value]);
    });
    return JSON.stringify([f.title.value, f.planning.value, groupValue(),
      f.status.value,
      pressed(f.halt), pressed(f.prototype),
                           bodyText(), answers]);
  }
  /* Whether anything changed, asked on demand -- at close, to decide
     whether to offer the discard prompt. It never gates Save. A disabled
     Save has to be driven by change events, and the body editor is the
     field most likely to be edited without one, so the button sat dead
     over a real edit until some other field was touched. The cure --
     being told to go type something -- is worse than the disease it
     prevents, which is only a write that changes nothing. */
  function dirty() { return clean !== null && snapshot() !== clean; }

  /* A tab. The label rides in `data-label` as well as in the text so the
     CSS can reserve the width the label will take when it goes bold on
     selection -- otherwise selecting a tab nudges every tab after it. */
  function makeTab(label, waiting) {
    var tab = document.createElement('button');
    tab.type = 'button';
    tab.className = 'aktab';
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-selected', 'false');
    tab.tabIndex = -1;
    if (waiting) {
      var dot = document.createElement('span');
      dot.className = 'aktabdot';
      /* The dot is the only thing saying this question is unanswered, so
         it needs a name of its own -- a colour is not a label. */
      dot.setAttribute('aria-label', 'unanswered');
      tab.appendChild(dot);
    }
    var text = document.createElement('span');
    text.className = 'aktabt';
    text.dataset.label = label;
    text.textContent = label;
    tab.appendChild(text);
    tab.addEventListener('click', function () {
      var all = Array.prototype.slice.call(tabs.querySelectorAll('.aktab'));
      showTab(all.indexOf(tab));
    });
    return tab;
  }

  /* Show one pane and mark its tab. `hidden` is the switch rather than a
     class, so a pane's boxes stay in the DOM and the save path goes on
     finding every answer whichever tab is open. */
  function showTab(i) {
    var panes = [details].concat(
      Array.prototype.slice.call(qList.querySelectorAll('.akq')));
    /* Outcome is last, and only present when the card has one — so its
       index is simply the end of the list rather than a fixed slot. */
    if (!outcome.dataset.empty) { panes.push(outcome); }
    panes.forEach(function (pane, n) { pane.hidden = n !== i; });
    tabs.querySelectorAll('.aktab').forEach(function (tab, n) {
      tab.setAttribute('aria-selected', n === i ? 'true' : 'false');
      /* Only the selected tab is in the page's tab order: a tablist is
         one stop, and the arrow keys move within it. */
      tab.tabIndex = n === i ? 0 : -1;
    });
  }

  /* Arrow keys move within a tablist -- the behaviour a tablist is
     expected to have once it announces itself as one. */
  tabs.addEventListener('keydown', function (e) {
    var keys = {ArrowLeft: -1, ArrowRight: 1};
    if (!(e.key in keys)) { return; }
    var all = Array.prototype.slice.call(tabs.querySelectorAll('.aktab'));
    var at = all.indexOf(document.activeElement);
    if (at < 0) { return; }
    e.preventDefault();
    var next = (at + keys[e.key] + all.length) % all.length;
    all[next].focus();
    showTab(next);
  });

  /* One tab per question plus Details, and one PANE per question. The
     page recomputes nothing: which questions exist, and which are still
     waiting, are both decided by the reader. */
  function buildQuestions(b) {
    qList.replaceChildren();
    tabs.replaceChildren();
    var src = b.querySelectorAll('.akqsrc');
    qList.hidden = src.length === 0;
    /* A strip is worth having once there is somewhere to go: questions,
       an outcome, or both. `Details` alone is a tab that cannot be left,
       so the common card still gets none. */
    var extra = src.length + (b.querySelector('.akoutsrc') ? 1 : 0);
    tabs.hidden = extra === 0;
    /* The dialog takes a fixed height only while it has tabs, so a card
       with no questions keeps sizing itself to its content. */
    dlg.classList.toggle('aktabbed', extra > 0);
    if (extra) { tabs.appendChild(makeTab('Details', false)); }
    src.forEach(function (node) {
      var heading = node.dataset.heading;
      var text = node.querySelector('.akqtext');
      var wrap = document.createElement('label');
      wrap.className = 'akq';
      var head = document.createElement('span');
      head.className = 'akqhead';
      head.textContent = heading;
      /* No `waiting` pill here. The question's own TAB carries a dot when
         it is unanswered, and the board card carries the chip — a third
         copy inside the pane you opened by clicking that tab says
         nothing the last two did not. */
      /* The asker's context: what you need to decide, not somewhere to
         type. Written into the answer box it both buried the cursor and
         marked the question answered. */
      var ctx = node.querySelector('.akqctx');
      if (ctx && ctx.value.trim()) {
        var pre = document.createElement('div');
        pre.className = 'akqctx-view';
        ctx.value.trim().split('\n').forEach(function (line) {
          var row = document.createElement('div');
          row.textContent = line.replace(/^>\s?/, '');
          pre.appendChild(row);
        });
        wrap.appendChild(head);
        wrap.appendChild(pre);
        head = null;
      }
      /* The pane is hidden until its tab is picked; showTab does the
         revealing, including for the very first one. */
      wrap.hidden = true;
      wrap.setAttribute('role', 'tabpanel');
      tabs.appendChild(makeTab('Q' + (qList.children.length + 1),
                               node.dataset.answered === 'false'));
      var box = document.createElement('textarea');
      box.className = 'akqbox';
      box.rows = 3;
      box.value = text ? text.value : '';
      box.defaultValue = box.value;
      box.dataset.heading = heading;
      if (head) { wrap.appendChild(head); }
      wrap.appendChild(box);
      qList.appendChild(wrap);
    });
  }

  /* The card's outcome: cloned, not moved, the same way the dates are —
     the data block stays intact for the next open, and a card with none
     leaves an empty pane rather than whatever the last card left in it.
     `data-empty` is what showTab and the strip both read, so the pane's
     existence and its tab cannot disagree. */
  function buildOutcome(b) {
    var src = b.querySelector('.akoutsrc');
    /* The BODY, not the pane: the action row below it has to survive
       every open, and replaceChildren on the pane would take it. */
    outcomeBody.replaceChildren(src ? src.cloneNode(true)
                                    : document.createTextNode(''));
    if (src) { delete outcome.dataset.empty; }
    else { outcome.dataset.empty = '1'; }
    if (src) { tabs.appendChild(makeTab('Outcome', false)); }
  }

  /* The card as it reads: its chips and its prose, both cloned from the
     block the same way the outcome and the dates are, so the modal shows
     the reader's own rendering and derives nothing itself. Cloned, not
     moved — the block has to be intact for the next open — and replaced
     rather than appended, so a card with no prose leaves an empty pane
     instead of the last card's. */
  function buildView(b) {
    var chips = b.querySelector('.akvchips');
    var prose = b.querySelector('.akbodysrc');
    viewChips.replaceChildren(chips ? chips.cloneNode(true)
                                    : document.createTextNode(''));
    viewBody.replaceChildren(prose ? prose.cloneNode(true)
                                   : document.createTextNode(''));
  }

  /* View to edit, one way. Save ends the card and Close leaves it; going
     back would put the file's prose beside an editor holding something
     else, which is two answers to what the card says.

     `form.hidden` is the guard as well as the state, so a second click on
     the pencil cannot run this twice. */
  function startEditing() {
    if (!form.hidden) { return; }
    viewPane.hidden = true;
    form.hidden = false;
    /* The pencil now sits on the title line, outside the pane it acts on,
       so hiding that pane no longer hides it. There is no way back from
       edit mode short of Save or Close, and a button offering one would
       be lying. */
    editBtn.hidden = true;
    /* ONE field, reused across cards, so it is loaded here rather than
       left holding whatever card was edited last. `editing` is what says
       the field now answers for this card; before it, `bodyText()` reads
       the body the card was opened with. */
    host.value = docText;
    editing = true;
    f.title.focus();
  }

  editBtn.addEventListener('click', startEditing);


  /* A value the file holds but the closed list does not offer would read
     as empty in a select, and Save would then erase it. Both selects are
     closed lists over hand-edited data, so both need the same guard. */
  function offer(select, value, note) {
    if (!value) return;
    var known = Array.prototype.some.call(select.options, function (o) {
      return o.value === value;
    });
    if (!known) select.add(new Option(value + ' ' + note, value),
                           select.options[select.options.length - 1]);
  }

  /* Everything the modal shows for one card, and nothing about opening
     it. Split out of `open` because a card that changes underneath a
     reader is REFILLED in place — and `showModal()` on a dialog that is
     already open throws, so the two cannot be one function. */
  function fill(b) {
    var d = b.dataset;
    block = b;
    titleEl.textContent = d.title;
    idEl.textContent = d.id;
    f.title.value = d.title || '';
    offer(f.planning, d.planning, '(not on the ladder)');
    offer(f.group, d.group, '(not a listed area)');
    /* Both selects' blank state is the "none" option now, not the empty
       string a browser would otherwise report for no selection — an
       empty string here would select nothing and paint the box blank. */
    f.status.value = d.status || 'inbox';
    f.planning.value = d.planning || 'none';
    f.group.value = d.group || 'none';
    f.newGroup.value = '';
    f.newGroupRow.hidden = true;
    press(f.halt, d.halt === 'true');
    press(f.prototype, d.requiresPrototype === 'true');
    /* A prototype card is built for the owner to look at, so its halt is
       forced on wherever the state is set -- not only when they click the
       toggle. A row that already carried `requires_prototype` without
       `halt` would otherwise open with the pause locked OFF and no way to
       turn it on, and the queue would not stop behind it. */
    if (pressed(f.prototype)) { press(f.halt, true); }
    paintHandling();

    /* Every card opens in view mode, whatever the last one was left in. */
    var raw = b.querySelector('.akraw');
    docText = raw ? raw.value : '';
    editing = false;
    form.hidden = true;
    viewPane.hidden = false;
    editBtn.hidden = false;
    buildView(b);
    buildQuestions(b);
    buildOutcome(b);
    /* Open on the first question still waiting. Opening a card that is
       asking something and landing on the fields is how the answer box
       got missed: it was below an editor tall enough to hide it. With
       nothing waiting the card is here to be read, so Details it is. */
    var waiting = Array.prototype.slice.call(
      b.querySelectorAll('.akqsrc')).findIndex(function (node) {
        return node.dataset.answered === 'false';
      });
    showTab(waiting < 0 ? 0 : waiting + 1);
    /* The dates are rendered inside the data block because only Jinja can
       call the timestamp macro, but they belong under the body. Cloned,
       not moved: the block is the modal's source of truth and has to be
       intact the next time this card is opened. */
    var dates = b.querySelector('.akdates');
    dateSlot.replaceChildren(dates ? dates.cloneNode(true)
                                   : document.createTextNode(''));
    /* A card whose prototype EXISTS on disk shows the link in the
       toggle's place and hides the toggle, so the flag cannot be turned
       off underneath a directory nobody would then sweep. A card that
       only ASKED for one keeps the toggle: changing your mind before the
       work exists is a decision, not an orphan. Read from `.akproto`,
       which Jinja renders only when the directory is really there. */
    var proto = b.querySelector('.akproto a');
    protoLink.hidden = !proto;
    f.prototype.hidden = !!proto;
    /* Cleared, never just hidden: a hidden element keeping the previous
       card's href is the stale link this used to have, one attribute
       further down. */
    if (proto) { protoLink.href = proto.getAttribute('href'); }
    else { protoLink.removeAttribute('href'); }
    /* The branch a card was built on, reachable without a mouse. Cleared
       rather than left, for the same reason the link's href is. */
    branchName.hidden = !d.branch;
    /* Nothing to discard without a branch, and an inert button reads
       as a broken one. */
    discardBtn.hidden = !d.branch;
    branchName.lastElementChild.textContent = d.branch || '';
    clean = snapshot();
  }

  function open(b) {
    fill(b);
    /* Last card's refusal is not this card's news. */
    window.akQuiet();
    dlg.showModal();
    /* showModal focuses the first focusable thing it finds, which since
       the tabs arrived is the Details tab — so a card opening on a
       question showed a focus ring around a tab that was not even the
       selected one. Focus what the card was opened FOR: the answer box on
       a question, the pencil otherwise, which is the one thing view mode
       is for. */
    var pane = qList.querySelector('.akq:not([hidden]) .akqbox');
    (pane || editBtn).focus();
  }

  /* ── the open-card rule ──────────────────────────────────────────────
     The board behind an open modal keeps repainting; only the card being
     held needs protecting. Three branches, and the third is the one that
     matters.

     `akHeld` is DELIBERATE staleness: when the owner is editing a card an
     agent has just changed, the page does not take the new fingerprint.
     Deferring the repaint without deferring the fingerprint would let the
     next save through, and it would silently discard what the agent
     wrote. Holding it is what makes the refusal correct. */
  window.akHeld = false;

  /* Which pane is showing. View state belongs to the person looking:
     jumping to Details because an agent wrote an outcome reads as the
     page losing your place. */
  function selectedTab() {
    var tab = tabs.querySelector('.aktab[aria-selected="true"] .aktabt');
    return tab ? tab.dataset.label : null;
  }

  function restoreTab(label) {
    if (!label) { return; }
    var text = tabs.querySelector('.aktabt[data-label="' + label + '"]');
    /* A label that is gone -- a question deleted underneath -- leaves the
       default `fill` chose, which is the right answer for a card whose
       shape changed. */
    if (text) { text.parentNode.click(); }
  }

  /* Which cards have already been consented to for this edit. Asking
     twice is nagging about a decision already made. */
  var asked = {};

  /* What the dialog knows that its two buttons do not. "status, outcome"
     says the agent did not touch your prose; "body" says it did.
     Derived by diffing the card as it was opened against the one just
     fetched, which is nearly free and is the fact that decides it. */
  function changedFields(before, after) {
    var keys = ['title', 'status', 'planning', 'group', 'halt',
                'branchRequested', 'requiresPrototype', 'branch'];
    var moved = [];
    keys.forEach(function (key) {
      if (before.dataset[key] !== after.dataset[key]) { moved.push(key); }
    });
    var was = before.querySelector('.akraw');
    var now = after.querySelector('.akraw');
    if (was && now && was.value !== now.value) { moved.push('body'); }
    var wasOut = before.querySelector('.akoutsrc');
    var nowOut = after.querySelector('.akoutsrc');
    if ((wasOut && wasOut.innerHTML) !== (nowOut && nowOut.innerHTML)) {
      moved.push('outcome');
    }
    return moved;
  }

  /* The standing line for the rest of the edit, once the owner has
     chosen to override. It replaces a second dialog: having consented,
     being asked again is nagging about a decision already made. */
  function standing(on) {
    window.akBanners().forEach(function (pair) {
      if (on && pair[1]) {
        pair[1].textContent =
          'Overriding changes made since you opened this card.';
      }
      if (pair[0]) { pair[0].hidden = !on; }
    });
  }

  function conflict(id) {
    if (asked[id]) { standing(true); return; }
    asked[id] = true;
    window.akCard(id).then(function (fresh) {
      var moved = changedFields(block, fresh);
      ask('This card changed while you were editing',
          'Changed on disk: ' + (moved.join(', ') || 'unknown')
            + '\n\nHow do you want to resolve it? Each option throws the '
            + "other's work away.",
          /* Reload is the CONFIRM and takes the danger styling; Keep
             Editing is the cancel, which is what ESC resolves to.
             Nothing is written until Save is pressed, whereas Reload
             destroys what was typed the instant it is pressed -- so
             Keep Editing is the safe answer and Enter has to reach it. */
          'Reload Card', 'Keep Editing')
        .then(function (reload) {
          if (reload) { window.location.reload(); return; }
          /* Keep Editing. The next save omits the fingerprint, which is
             what the door already calls "do not check". */
          standing(true);
        });
    }).catch(function () { standing(true); });
  }

  function akOnChanged(ids) {
    if (!block || !dlg.open) { return; }
    var id = block.dataset.id;
    if (ids.indexOf(id) === -1) { return; }   /* not our card */
    if (dirty()) {
      window.akHeld = true;
      conflict(id);
      return;
    }
    var keep = selectedTab();
    var wasEditing = !form.hidden;
    window.akCard(id).then(function (fresh) {
      fill(fresh);
      restoreTab(keep);
      /* The pencil had been clicked, so the editor stays open -- on the
         file's new text, which is what it would have been handed had the
         card been opened a second later. Nothing was typed, or `dirty()`
         would have sent this down the branch above. */
      if (wasEditing) { startEditing(); }
    }).catch(function () { /* the offline note already says it */ });
  }

  document.addEventListener('akchanged', function (e) {
    akOnChanged(e.detail || []);
  });

  /* Picking "New area…" reveals the text box and puts the cursor in it;
     picking anything else puts it away, so the form has one answer. */
  f.group.addEventListener('change', function () {
    var adding = f.group.value === '__new__';
    f.newGroupRow.hidden = !adding;
    if (adding) f.newGroup.focus();
  });

  /* Status is editable right here, so the toggles have to follow it
     live — changing a card from Done to Ready and finding its handling
     still locked would read as the modal being broken. */
  f.status.addEventListener('change', paintHandling);

  [f.halt, f.prototype].forEach(function (el) {
    el.addEventListener('click', function () {
      press(el, !pressed(el));
      /* A prototype is built for the owner to look at, so "build a design
         pass then merge whatever came out" is not a state anyone wants.
         Refused at the point of entry rather than corrected later. */
      if (el === f.prototype && pressed(f.prototype)) { press(f.halt, true); }
      paintHandling();
    });
  });

  /* Delegated at the board, not bound per tile: the live reconciler
     clones fresh tiles in, and a listener attached at load would not be
     on them. `data-id` is the address — the card's own id, which a
     delete cannot shift the way a file-order number could. */
  if (board) {
    board.addEventListener('click', function (e) {
      var card = e.target instanceof Element
        ? e.target.closest('.akcard') : null;
      if (!card) { return; }
      if (card.dataset.justDragged) { return; }  /* a drag is not a click */
      window.akCard(card.dataset.id).then(open).catch(function () {
        /* Never open onto empty fields. An empty form over a card that
           has content is how an accidental blanking save happens. */
        window.akBanners().forEach(function (pair) {
          if (pair[1]) pair[1].textContent =
            'That card could not be loaded. It may have been deleted, or '
            + 'the server may be down.';
          if (pair[0]) pair[0].hidden = false;
        });
      });
    });
  }

  function save() {
    if (!block) return;
    var id = block.dataset.id;
    var group = groupValue();
    var doc = bodyText();
    var body = new URLSearchParams();
    body.set('title', f.title.value);
    body.set('planning', f.planning.value);
    body.set('group', group);
    /* Never an empty value: a POST form field with no text is turned
       into no value at all before this route ever sees it, so an
       unchecked box still has to say so out loud. */
    body.set('halt', pressed(f.halt) ? 'on' : 'off');
    body.set('requires_prototype', pressed(f.prototype) ? 'on' : 'off');
    /* The BODY, not the whole file: the sections with tabs of their own
       are not editable here, and the door is what puts this back into the
       prose it came from. Sending `body` would send a card's Questions
       and Outcome as if this editor had been holding them. */
    body.set('overview', doc);
    /* Only boxes whose text actually changed are sent: an untouched
       question must not be rewritten, because rewriting it would restamp
       a section the owner never opened. */
    var answers = [];
    qList.querySelectorAll('.akqbox').forEach(function (box) {
      if (box.value !== box.defaultValue) {
        answers.push({heading: box.dataset.heading, text: box.value});
      }
    });
    if (answers.length) body.set('answers', JSON.stringify(answers));
    /* Held means the owner chose to override: send no fingerprint, which
       is what the door already reads as "do not check". Same path the
       loop writes on -- no force flag and no second code path on the
       server. */
    if (!window.akHeld) {
      body.set('fingerprint', board.dataset.fingerprint);
    }
    window.akSend('PATCH', '/cards/' + encodeURIComponent(id), body)
      .then(function (data) {
        /* A status change is a MOVE, not an edit. `status` and `rank`
           belong to the drag, and `amik_edit.move` is their only writer
           — so this posts to the same route the drag does rather than
           teaching the edit route a field it refuses on purpose. It runs
           after the field write so a stale fingerprint refuses before
           anything moves, and it carries the fingerprint that write just
           returned. A dropdown has no drop position, so it appends; the
           door clamps an index past the end.

           FIRST, before the answers branch below reloads: a save can
           carry both, and answering a question on a blocked card sends
           it back to Ready on its own. A reload here would drop the
           dropdown's pick on the floor and leave the derived move
           looking like it had overruled a choice the owner made out
           loud. This posts last, so that choice is the one that lands. */
        if (f.status.value !== (block.dataset.status || 'inbox')) {
          var mv = new URLSearchParams();
          mv.set('id', id);
          mv.set('to_status', f.status.value);
          mv.set('to_index', String(document.querySelectorAll(
            '.akcol[data-status="' + f.status.value + '"] .akcard').length));
          mv.set('fingerprint', data.fingerprint);
          window.akSend('PATCH', '/cards/' + encodeURIComponent(mv.get('id')) + '/position', mv).then(function () {
            /* The card changes column, the counts change, the empty-state
               text changes. Repainting all of that by hand is a second
               source of truth; the server already renders it. */
            window.location.reload();
          });
          return;
        }
        /* Answering changes derived state this page does not recompute —
           the waiting count, the chip, and the column itself, since the
           last answer on a blocked card moves it back to Ready — so a
           save that carried answers reloads rather than patching the
           DOM. */
        if (answers.length) { window.location.reload(); return; }
        board.dataset.fingerprint = data.fingerprint;
        /* Write the saved values BACK into the block the modal reads from.
           Without this the block stays at page-load state: reopening the
           card showed the pre-save values, and a second Save posted them,
           silently reverting the first edit while reporting success. The
           fingerprint cannot catch that — this page is the writer. */
        block.dataset.title = f.title.value;
        block.dataset.planning = f.planning.value;
        block.dataset.group = group;
        block.dataset.halt = pressed(f.halt) ? 'true' : 'false';
        block.dataset.requiresPrototype =
          pressed(f.prototype) ? 'true' : 'false';
        var raw = block.querySelector('.akraw');
        if (raw) raw.value = doc;
        /* The modal's own view of the card, re-derived and re-rendered by
           the server for the same reason the tile's chips are: a chip is
           the reader's rule and the prose is the reader's boundary, and
           what a reopened card shows has to be what the file now says. */
        var vsrc = block.querySelector('.akvsrc');
        if (vsrc && typeof data.view === 'string') { vsrc.innerHTML = data.view; }
        /* A brand-new area has to join both selects' option lists, or the
           next card opened would not be able to pick what was just made. */
        offer(f.group, group, '(not a listed area)');
        /* The card face is server-rendered; repaint what the modal owns.
           The chips come back from the save already derived and already
           rendered — the conflict pill, the question flag and a rung's
           blocking styling are the reader's rules, so this paints what
           the server sent and never computes one itself. An empty string
           means the card has nothing left to show, which is how a tile
           LOSES a chip. */
        var card = document.querySelector(
          '.akcard[data-id="' + id + '"]');
        if (card) {
          card.querySelector('.aktitle').textContent = f.title.value;
          var old = card.querySelector('.akchips');
          if (old) old.remove();
          if (data.chips) card.insertAdjacentHTML('beforeend', data.chips);
        }
        clean = snapshot();
        dlg.close();          /* Save is an ending, not a checkpoint */
      })
      .catch(function () { /* akSend already said why */ });
  }

  saveBtn.addEventListener('click', save);

  /* Delete is terminal and git is the only undo, so it asks first. The
     server refuses while another row still points here and says which
     ones; that reason reaches the page through akSend's banner. */
  /* The way out of a bad outcome, and the only verdict that needs a
     control. Every other one is a DESTINATION, and destinations clean
     up after themselves however you reach them — Done lands the card,
     Abandoned drops its branch, answering the last question returns it
     to Ready on its own. Throwing the build away and going again has
     no status to drag to: dragging to Ready keeps the branch, and the
     next run would resume the very attempt being rejected.

     The confirm asks for feedback, because the moment you decide to
     retry is when you know what went wrong — and asking then beats
     making someone find a spot for it afterwards. */
  var discardBtn = document.getElementById('akdiscard');

  discardBtn.addEventListener('click', function () {
    if (!block) return;
    var id = block.dataset.id;
    var branch = block.dataset.branch || 'card/' + id;
    ask('Try Again…',
        'Throws away what the agent built. The branch ' + branch
        + ' and any prototype go.\n\n'
        + 'The card goes back to Ready, so the loop will pick it up '
        + 'again.\n\n'
        + 'Your answers stay. So does the outcome above, marked as '
        + 'discarded — it is what the next attempt should not repeat.',
        'OK', 'Cancel',
        "Do you have feedback for the agent? Share it here and we'll "
        + 'try again…')
      .then(function (answer) {
        if (!answer.ok) return;
        var body = new URLSearchParams();
        body.set('feedback', answer.text);
        window.akSend('DELETE', '/cards/' + encodeURIComponent(id)
                      + '/work', body)
          .then(function () {
            clean = null;
            dlg.close();
            window.location.reload();
          })
          .catch(function () { clean = null; dlg.close(); });
      });
  });

  document.getElementById('akdelete').addEventListener('click', function () {
    if (!block) return;
    var id = block.dataset.id;
    ask('Delete this item?',
        '\u201C' + block.dataset.title + '\u201D will be removed from the '
        + 'board. There is no undo in the app.', 'Delete')
      .then(function (ok) {
        if (!ok) return;
        var body = new URLSearchParams();
        body.set('fingerprint', board.dataset.fingerprint);
        window.akSend('DELETE', '/cards/' + encodeURIComponent(id), body)
          .then(function () {
            /* Reload rather than splice the card out here: the server owns
               every rank the removal shifted, and a hand-patched board
               would be a second source of truth. clean is dropped first so
               the close cannot raise the discard prompt over a row that no
               longer exists. */
            clean = null;
            dlg.close();
            window.location.reload();
          })
          /* Closed on a refusal too, because the banner that carries the
             server's reason is on the PAGE and a modal would sit over it.
             Any unsaved edit goes with it — acceptable only because the
             gesture that got here was a confirmed Delete. */
          .catch(function () { clean = null; dlg.close(); });
      });
  });

  /* Unsaved work should not leave quietly — the same rule the page editor
     keeps, minus its beforeunload, which a dialog never fires. ask() is
     base.html's themed <dialog>; window.confirm is banned here because a
     browser will offer to suppress it permanently. */
  function leave() {
    if (!dirty()) { dlg.close(); return; }
    ask('Discard changes?',
        'This item has unsaved edits.', 'Discard').then(function (ok) {
      if (ok) { clean = null; dlg.close(); }
    });
  }
  document.getElementById('akclose').addEventListener('click', leave);
  dlg.addEventListener('cancel', function (e) {        /* ESC */
    if (dirty()) { e.preventDefault(); leave(); }
  });

  /* A consent to override belongs to ONE edit of ONE card. Cleared on the
     dialog's own close event, so every way out of the card -- Save,
     Close, ESC, a click on the backdrop -- clears it, and the next card
     opened sends its fingerprint like any other. */
  dlg.addEventListener('close', function () {
    window.akHeld = false;
    asked = {};
    standing(false);
  });

  /* ── the + on Inbox ───────────────────────────────────────────────────
     The dialog, the chord and the POST all live in quickadd.js, which
     base.html loads on every page. This button is just another way in, so
     it calls the same entry point rather than keeping a second copy that
     could drift. */
  var add = document.querySelector('.addbtn');
  if (add) {
    /* Resolved on CLICK, never here. base.html includes the quick-add
       partial — and its script — after the content block, so this file
       runs first and the global does not exist yet. Reading it at attach
       time silently bound nothing: no error, no warning, a button that
       did nothing, while Cmd/Ctrl+K kept working because it registers
       inside the file that defines it. */
    add.addEventListener('click', function () {
      if (window.amikQuickAdd) { window.amikQuickAdd(); }
    });
  }
})();


/* ── what this browser remembers of the view ───────────────────────────
   Which columns you had shut, and how far across you had scrolled. Both
   are VIEW, not data: they belong to the person looking, so they live in
   localStorage rather than in `board.jsonl`, which is the project's file
   and travels through git to every other reader.

   Keyed by mount point, because the same origin can serve a board
   standalone and a board embedded under /amik, and one reader's shut
   columns are not the other's.

   Every access is wrapped. localStorage THROWS on the READ in a browser
   with site data turned off — not returning null, throwing — and an
   exception here runs at file scope, so it would take every listener
   below it with it. A browser that cannot store simply forgets. */
window.akView = (function () {
  function key(name) { return 'amik:' + window.akBase() + ':' + name; }
  return {
    read: function (name, fallback) {
      try {
        var raw = window.localStorage.getItem(key(name));
        return raw === null ? fallback : JSON.parse(raw);
      } catch (e) { return fallback; }
    },
    write: function (name, value) {
      try {
        window.localStorage.setItem(key(name), JSON.stringify(value));
      } catch (e) { /* disabled, or full */ }
    }
  };
})();


/* ── collapsing ────────────────────────────────────────────────────────
   Done, Someday and Won't Do are most of the file and none of it is work in
   flight, so they arrive shut. Not <details>, whose UA marker would be the
   one thing on this page the browser styles for us.

   Those are the DEFAULTS, and what is remembered is only the columns you
   have actually clicked — one entry per toggle, keyed by status, never a
   snapshot of the whole board. So a column you have never touched still
   follows the server's default, and a column added tomorrow arrives the
   way it was designed to rather than in whatever state a snapshot taken
   today happened to freeze.

   A column the DRAG opens is deliberately not written down: that one
   opens itself to accept a card and shuts again on dragend. Only your
   own click is a decision about how you want the board to look. */
(function () {
  var shut = window.akView.read('columns', {});
  if (!shut || typeof shut !== 'object') shut = {};

  document.querySelectorAll('.akcol').forEach(function (col) {
    var head = col.querySelector('.akcolhead');
    var status = col.dataset.status;
    if (Object.prototype.hasOwnProperty.call(shut, status)) {
      col.classList.toggle('akcollapsed', !!shut[status]);
      head.setAttribute('aria-expanded', shut[status] ? 'false' : 'true');
    }
    head.addEventListener('click', function () {
      var now = col.classList.toggle('akcollapsed');
      head.setAttribute('aria-expanded', now ? 'false' : 'true');
      shut[status] = now;
      window.akView.write('columns', shut);
    });
  });
})();


/* ── how far across you were ───────────────────────────────────────────
   Nine columns do not fit, so the board scrolls sideways, and a refresh
   used to throw you back to Inbox — the one end you were not reading.

   Restored AFTER the collapse state above, because a shut column is
   130px narrower and restoring the offset first would land it somewhere
   else. Writes are coalesced: a scroll fires once a frame, and
   serialising on each one would be a write per frame for the length of
   a flick. */
(function () {
  var board = document.querySelector('.akboard');
  if (!board) return;

  var at = window.akView.read('scroll', 0);
  if (typeof at === 'number' && at > 0) board.scrollLeft = at;

  var timer = null;
  board.addEventListener('scroll', function () {
    if (timer) return;
    timer = setTimeout(function () {
      timer = null;
      window.akView.write('scroll', Math.round(board.scrollLeft));
    }, 150);
  });
})();


/* ── drag to reorder, drag across to restatus ──────────────────────────
   The dragged card moves through the DOM as the pointer travels, so the
   preview IS the result rather than a separate indicator that could
   disagree with it. Every path that does not end in a committed write puts
   the card back, so the board never shows an order the file does not have:
   a refused POST, and — the case a previous fix missed — a drag released
   anywhere that is not a drop zone, which after that fix includes an open
   column's own header and padding. */
(function () {
  var board = document.querySelector('.akboard');
  if (!board) return;
  var dragged = null, home = null, dropped = false;
  var openedCols = [], pending = false;

  function counts() {
    board.querySelectorAll('.akcol').forEach(function (col) {
      var n = col.querySelectorAll('.akcard').length;
      var pill = col.querySelector('.akcount');
      pill.textContent = n;
      pill.hidden = !n;             /* a "0" says nothing the words do not */
      var empty = col.querySelector('.akempty');
      if (empty) empty.hidden = n > 0;
    });
  }

  function restore(card, from) {
    if (!from) return;
    if (from.next && from.next.parentNode === from.drop) {
      from.drop.insertBefore(card, from.next);
    } else {
      from.drop.appendChild(card);
    }
    counts();
  }

  function shut(col) {
    col.classList.add('akcollapsed');
    col.querySelector('.akcolhead').setAttribute('aria-expanded', 'false');
  }

  /* The card the pointer sits above, by midpoint — the one the dragged
     card should be inserted BEFORE. null means "past the last card". */
  function before(drop, y) {
    var cards = [].slice.call(drop.querySelectorAll('.akcard'))
      .filter(function (c) { return c !== dragged; });
    for (var i = 0; i < cards.length; i++) {
      var box = cards[i].getBoundingClientRect();
      if (y < box.top + box.height / 2) return cards[i];
    }
    return null;
  }

  board.querySelectorAll('.akcard').forEach(function (card) {
    card.addEventListener('dragstart', function (e) {
      /* One write at a time. A second drag started before the first
         response would post the PREVIOUS fingerprint and be told the
         board changed on disk — by its own predecessor. */
      if (pending) { e.preventDefault(); return; }
      dragged = card;
      dropped = false;
      /* Captured per drag, not on the module: the next dragstart used to
         overwrite these, so a failed restore could put a card back into
         a slot that had since moved. */
      home = {drop: card.parentNode, next: card.nextElementSibling};
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      /* Firefox starts no drag at all without payload on the transfer. */
      e.dataTransfer.setData('text/plain', card.dataset.id);
    });
    card.addEventListener('dragend', function () {
      card.classList.remove('dragging');
      /* No drop means no write, so the move that the dragover previewed
         has to be undone. Releasing over an open column's header or
         padding lands here, and aiming at the top of a long column is
         exactly the gesture that puts you there. */
      if (!dropped) restore(card, home);
      openedCols.forEach(function (col) {
        if (!col.contains(card)) shut(col);
      });
      openedCols = [];
      /* Survives one click: the browser fires click after a cancelled
         drag, and that click must not open the modal. */
      card.dataset.justDragged = '1';
      setTimeout(function () { delete card.dataset.justDragged; }, 0);
      dragged = null;
      /* A drag that committed nothing ends here, so whatever the live
         board deferred can go on screen. One that DID commit is still
         writing; `commit` fires this again when its write lands. */
      document.dispatchEvent(new CustomEvent('akgestureend'));
    });
  });

  /* A shut column hides its own drop zone, so the column takes the first
     dragover and opens itself. preventDefault ONLY here: an open column's
     header and padding are not drop targets, and saying otherwise would
     accept a drag that commits nothing. */
  board.querySelectorAll('.akcol').forEach(function (col) {
    col.addEventListener('dragover', function (e) {
      if (!dragged || !col.classList.contains('akcollapsed')) return;
      e.preventDefault();
      col.classList.remove('akcollapsed');
      col.querySelector('.akcolhead').setAttribute('aria-expanded', 'true');
      if (openedCols.indexOf(col) < 0) openedCols.push(col);
    });
  });

  board.querySelectorAll('.akdrop').forEach(function (drop) {
    drop.addEventListener('dragover', function (e) {
      if (!dragged) return;
      e.preventDefault();                    /* required to allow a drop */
      e.dataTransfer.dropEffect = 'move';
      var ref = before(drop, e.clientY);
      if (ref) drop.insertBefore(dragged, ref);
      else drop.appendChild(dragged);
      counts();
    });
    drop.addEventListener('drop', function (e) {
      e.preventDefault();
      if (!dragged) return;
      /* A drop on a zone that never saw a dragover has not moved the card
         into it, and indexOf would answer -1. Nothing to commit. */
      var cards = [].slice.call(drop.querySelectorAll('.akcard'));
      var at = cards.indexOf(dragged);
      if (at < 0) return;
      dropped = true;
      commit(dragged, drop, at, home);
    });
  });

  function commit(card, drop, at, from) {
    var col = drop.closest('.akcol');
    var body = new URLSearchParams();
    body.set('id', card.dataset.id);
    body.set('to_status', col.dataset.status);
    body.set('to_index', at);
    body.set('fingerprint', board.dataset.fingerprint);
    pending = true;
    /* Declared on the board so the live reconciler can see it. A repaint
       between the drop and the response would fetch a board that does not
       carry this move yet and put the card back where it came from. */
    board.dataset.writing = '1';
    window.akSend('PATCH', '/cards/' + encodeURIComponent(body.get('id')) + '/position', body)
      .then(function (data) {
        board.dataset.fingerprint = data.fingerprint;
      })
      .catch(function () {
        restore(card, from);            /* the file won it */
      })
      .then(function () {
        pending = false;
        delete board.dataset.writing;
        document.dispatchEvent(new CustomEvent('akgestureend'));
      });
  }
})();

/* ── the play/pause toggle ──────────────────────────────────────────────
   One line in amik.toml, `armed`, which the loop re-reads every tick. So
   the button promises a DECLARATION and nothing about a daemon: flipping
   it changes what the next tick is allowed to do, and that is all.

   Pausing does NOT stop work already under way — the loop hands a card to
   an agent and that agent runs to the end. Anything sitting in Doing is
   going to finish, so a pause that lands on a non-empty Doing column says
   so. The count comes back from the server's own fresh read rather than
   from this page, which may have been open for hours.

   Both wordings and both glyphs are server-rendered; this only moves
   `data-armed` and copies the matching strings across. A second copy of
   either here is how a label and its state drift apart.

   Delegated at the document rather than bound to the button, because the
   live board repaints the top bar this button sits in — a listener
   attached at load would go with the node it was attached to, and the
   pill would quietly stop responding after the first repaint. */
(function () {
  var note = document.getElementById('akarmnote');
  var msg = document.getElementById('akarmmsg');

  function paint(btn, armed) {
    btn.dataset.armed = armed ? 'true' : 'false';
    btn.dataset.tip = armed ? btn.dataset.armedTip : btn.dataset.pausedTip;
    btn.setAttribute('aria-label',
      armed ? btn.dataset.armedLabel : btn.dataset.pausedLabel);
  }

  document.addEventListener('click', function (e) {
    var btn = e.target instanceof Element
      ? e.target.closest('#akarmbtn') : null;
    if (!btn) return;
    if (btn.disabled) return;
    var want = btn.dataset.armed !== 'true';
    var body = new URLSearchParams();
    body.set('armed', want ? 'true' : 'false');
    btn.disabled = true;
    if (note) note.hidden = true;
    window.akSend('PATCH', '/project', body)
      .then(function (data) {
        paint(btn, data.armed);
        var n = data.working || 0;
        if (!data.armed && n && msg && note) {
          msg.textContent = 'Paused. '
            + (n === 1 ? 'The card in Doing will finish'
                       : 'The ' + n + ' cards in Doing will finish')
            + ' — nothing new will be picked up.';
          note.hidden = false;
        }
      })
      .catch(function () { /* akSend already said why */ })
      .then(function () { btn.disabled = false; });
  });
})();

/* ── the live board ────────────────────────────────────────────────────
   The server watches the files and says when something moved; this
   fetches what moved and puts it on screen. The server remains the only
   thing that RENDERS -- a chip's meaning, a column's count and a rung's
   blocking styling are the reader's rules, and deriving any of them here
   would make the page a second source of truth for them.

   What must survive a repaint is view state: which columns are shut, how
   far each is scrolled, and any gesture in flight. The rule that covers
   the first two is to reconcile a column's CARDS and never the column
   element -- its scroll offset and its .akcollapsed class are then never
   destroyed, so they need no restoring. */
window.akLive = (function () {
  var board = document.querySelector('.akboard');
  if (!board) { return null; }
  /* Whether a repaint is OWED, not a stored copy of one. Holding the
     markup would mean applying a render fetched before the gesture
     started; owing one means fetching current markup when the gesture
     ends. Three deferred renders are not three updates to apply in
     order, they are two stale ones and a current one. */
  var pending = false;

  function busy() {
    /* A gesture is in flight: a dialog is open, a card is being dragged,
       or a drag's write has not come back yet. Moving the floor under any
       of them is how a drop lands on the wrong column, an open modal
       loses the node it writes to, and a committed move is undone by a
       fetch that set off before the server had it. */
    return !!document.querySelector('dialog[open]')
        || !!document.querySelector('.akcard.dragging')
        || !!board.dataset.writing;
  }

  function offline(on) {
    var note = document.getElementById('akoffline');
    if (note) { note.hidden = !on; }
  }

  /* One region, replaced wholesale. Safe because everything inside is
     server-rendered and nothing inside owns a listener: the arm pill's
     click is delegated at the document for exactly this reason. */
  function repaint(fresh, selector) {
    var slot = document.querySelector(selector);
    var theirs = fresh.querySelector(selector);
    if (slot && theirs) { slot.innerHTML = theirs.innerHTML; }
  }

  function reconcile(fresh) {
    /* `fresh` is a parsed document of the board page. Walk its cards and
       move ours to match, keyed on data-id so an unchanged card keeps
       its DOM node -- and with it its focus, its hover and any
       transition it is part of. */
    fresh.querySelectorAll('.akcol').forEach(function (col) {
      var mine = board.querySelector('.akcol.ak-' + col.dataset.status);
      if (!mine) { return; }
      /* .akdrop is the card host AND the drop zone. The empty-column
         invitation lives inside it on purpose -- an empty column's
         message has to be the thing that accepts a drop. */
      var host = mine.querySelector('.akdrop');
      var from = col.querySelector('.akdrop');
      if (!host || !from) { return; }
      var seen = {};
      Array.prototype.forEach.call(from.querySelectorAll('.akcard'),
        function (card, i) {
          var id = card.dataset.id;
          seen[id] = true;
          var here = id
            ? host.querySelector('.akcard[data-id="' + id + '"]') : null;
          if (here) {
            /* Chips are derived, so they come from the server's copy. */
            var chips = here.querySelector('.akchips');
            var fresher = card.querySelector('.akchips');
            if (chips) { chips.remove(); }
            if (fresher) { here.appendChild(fresher.cloneNode(true)); }
            var title = here.querySelector('.aktitle');
            var newTitle = card.querySelector('.aktitle');
            if (title && newTitle) { title.innerHTML = newTitle.innerHTML; }
          } else {
            here = card.cloneNode(true);
          }
          var mineCards = host.querySelectorAll('.akcard');
          if (mineCards[i] !== here) {
            host.insertBefore(here, mineCards[i] || null);
          }
        });
      Array.prototype.forEach.call(host.querySelectorAll('.akcard'),
        function (card) {
          if (!seen[card.dataset.id]) { card.remove(); }
        });
      /* The count is the reader's, not ours. */
      var count = mine.querySelector('.akcount');
      var fromCount = col.querySelector('.akcount');
      if (count && fromCount) {
        count.textContent = fromCount.textContent;
        count.hidden = fromCount.hidden;
      }
      /* The empty-column invitation appears and disappears with the
         cards, and it is a drop target, so it cannot be left behind. */
      var mineEmpty = mine.querySelector('.akempty');
      var fromEmpty = col.querySelector('.akempty');
      if (mineEmpty && !fromEmpty) { mineEmpty.remove(); }
      if (!mineEmpty && fromEmpty) {
        /* First child of the drop zone, never a sibling of it: outside,
           it would render but refuse the drop it is inviting. */
        host.insertBefore(fromEmpty.cloneNode(true), host.firstChild);
      }
    });
    /* Outside the board region and live all the same. The top bar
       carries the arm/pause pill, which is what someone watches while
       the loop runs, and the git block carries the branch and what just
       landed -- with most work going straight to master, that list is
       the review surface. The <details> element itself survives, so an
       open log stays open. */
    repaint(fresh, '#aktopbar');
    repaint(fresh, '.akgit');
    /* The whole point of the card. The page could not refresh its own
       fingerprint before this, so the first foreign write shut a door
       that stayed shut until a reload. */
    var freshBoard = fresh.querySelector('.akboard');
    if (freshBoard) {
      board.dataset.fingerprint = freshBoard.dataset.fingerprint;
    }
  }

  function apply(html) {
    var fresh = new DOMParser().parseFromString(html, 'text/html');
    if (!fresh.querySelector('.akboard')) { return; }
    reconcile(fresh);
  }

  function refresh() {
    if (busy()) { pending = true; return Promise.resolve(); }
    pending = false;
    return fetch(window.akBase() + '/')
      .then(function (r) {
        if (!r.ok) { throw r.status; }
        return r.text();
      })
      .then(function (html) { offline(false); apply(html); })
      /* The last good render stays. A board wiped because one fetch
         failed is worse than a board a few seconds old. */
      .catch(function () { offline(true); });
  }

  /* Flush whatever was deferred while a gesture was in flight. Every
     dialog on the page fires `close`, and a drag fires this itself, so
     there is one rule here rather than a call at each place a gesture
     can end. */
  function flush() { if (pending && !busy()) { refresh(); } }
  document.addEventListener('akgestureend', flush);
  document.querySelectorAll('dialog').forEach(function (dlg) {
    dlg.addEventListener('close', flush);       /* `close` does not bubble */
  });

  var feed = new EventSource(window.akBase() + '/events');
  feed.onmessage = function (e) {
    var payload;
    try { payload = JSON.parse(e.data); } catch (err) { return; }
    /* The ids ALWAYS go out, even while a gesture defers the repaint:
       the open-card rule is the one listener that most needs to hear
       about a change it is deliberately not painting. */
    document.dispatchEvent(new CustomEvent('akchanged',
      {detail: payload.changed || []}));
    if (payload.fingerprint === board.dataset.fingerprint && !pending) {
      return;                       /* already current */
    }
    refresh();
  };
  /* EventSource retries on its own, so there is nothing to do here but
     say so on screen. */
  feed.onerror = function () { offline(true); };

  return {apply: apply, refresh: refresh,
          get pending() { return pending; }};
})();
