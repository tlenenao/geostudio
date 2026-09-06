(function(){
  "use strict";

  /* 1. lire les données embarquées — même source que le Markdown, même passage. */
  var DATA = JSON.parse(document.getElementById("bilan-data").textContent);
  var FEATURES = DATA.fonctionnalites;
  var total = FEATURES.length;
  FEATURES.forEach(function(r, i){ r._idx = i; });

  /* Plancher de priorité haute : dupliqué depuis
     core/scripts/feature_health_thresholds.json (plancher_priorite_haute).
     Affichage seul — la porte réelle est `feature_health_cli.py --check`,
     ce nombre n'a ici qu'une valeur d'information pour la tuile de synthèse. */
  var CI_FLOOR_HAUTE = 40;

  var PRIORITY_ORDER = ["haute", "moyenne", "basse"];
  var PRIORITY_CLASS = { haute: "pri-hi", moyenne: "pri-mid", basse: "pri-lo" };

  /* REV-180 : la (grande) majorité des priorités de l'inventaire vient de
     l'amorçage automatique SP-42, jamais revue manuellement — rien ne le
     signalait ici avant ce correctif. "declaree" est déjà la valeur par
     défaut du modèle Python (priorité posée à la main dès la création d'une
     entrée, cf. feature_health/model.py) ; "manuel-sp61" désigne les 3
     entrées effectivement revues pendant la clôture de SP-61. Seul le reste
     (essentiellement "amorcage-sp42") est encore amorcé. */
  var REVIEWED_PRIORITY_SOURCES = { declaree: true, "manuel-sp61": true };
  function isReviewedPrioritySource(source){
    return !!REVIEWED_PRIORITY_SOURCES[source];
  }
  var SUBSCORE_KEYS = ["tests", "atteignabilite", "garde", "dette"];
  var SUBSCORE_LABEL = {
    tests: "Tests", atteignabilite: "Atteignabilité", garde: "Garde", dette: "Dette"
  };
  var HEALTH_BRACKET_ORDER = ["low", "mid", "good", "great", "na"];
  var HEALTH_BRACKET_LABEL = {
    low: "< 40", mid: "40 – 70", good: "70 – 90", great: "≥ 90", na: "Non mesurable"
  };

  function esc(s){
    if (s === null || s === undefined) return "";
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  function healthLevel(v){
    if (v === null || v === undefined) return "na";
    if (v < 40) return "low";
    if (v < 70) return "mid";
    if (v < 90) return "good";
    return "great";
  }
  function healthColor(level){
    return level === "na" ? "var(--ink-3)" : "var(--note-" + level + ")";
  }
  function healthBadge(v){
    if (v === null || v === undefined) return '<span style="color:var(--ink-3)">—</span>';
    var lvl = healthLevel(v);
    return '<span class="note-badge lvl-' + lvl + ' tabular">' + v.toFixed(1) + '</span>';
  }
  function priorityBadge(p, source){
    var cls = PRIORITY_CLASS[p] || "pri-lo";
    if (isReviewedPrioritySource(source)) {
      return '<span class="pri-badge ' + cls + ' tabular">' + esc(p) + '</span>';
    }
    return '<span class="pri-badge ' + cls + ' unreviewed tabular" ' +
      'title="Priorité encore amorcée (' + esc(source) + '), jamais revue manuellement">' +
      esc(p) + ' <span aria-hidden="true">&middot;</span></span>';
  }
  function deltaCell(delta){
    if (delta === null || delta === undefined) return '<span style="color:var(--ink-3)">—</span>';
    if (Math.abs(delta) < 0.05) return '<span class="tabular">=</span>';
    var sign = delta > 0 ? "+" : "";
    var color = delta > 0 ? "var(--note-good)" : "var(--note-low)";
    var arrow = delta > 0 ? "↑" : "↓";
    return '<span class="tabular" style="color:' + color + ';font-weight:600">' +
      arrow + " " + sign + delta.toFixed(1) + "</span>";
  }
  function subCell(score){
    if (!score || score.valeur === null || score.valeur === undefined) {
      return '<span style="color:var(--ink-3)">—</span>';
    }
    return '<span class="tabular">' + score.valeur.toFixed(1) + "</span>";
  }

  /* ==================================================================
     2. tuiles de synthèse + barre empilée (fixes, jamais filtrées)
     ================================================================== */
  var globalBuckets = { low: 0, mid: 0, good: 0, great: 0, na: 0 };
  FEATURES.forEach(function(r){ globalBuckets[healthLevel(r.sante)]++; });
  var measured = FEATURES.map(function(r){ return r.sante; }).filter(function(v){ return v !== null && v !== undefined; });

  function renderStackBar(){
    var bar = document.getElementById("stackBar");
    bar.innerHTML = HEALTH_BRACKET_ORDER.map(function(k){
      var pct = total ? (globalBuckets[k] / total * 100) : 0;
      return '<span style="width:' + pct.toFixed(3) + '%;background:' + healthColor(k) + '" title="' +
             HEALTH_BRACKET_LABEL[k] + " — " + globalBuckets[k] + '"></span>';
    }).join("");
  }

  function renderTiles(){
    var order = [["low","< 40"],["mid","40 – 70"],["good","70 – 90"],["great","≥ 90"],["na","Non mesurable"]];
    var html = order.map(function(pair){
      var k = pair[0];
      var color = healthColor(k);
      return '<div class="tile" style="border-top-color:' + color + '"><div class="n tabular" style="color:' +
             color + '">' + globalBuckets[k] + '</div><div class="l">' + pair[1] + '</div></div>';
    }).join("");
    html += '<div class="tile total"><div class="n tabular">' + total + '</div><div class="l">Total</div></div>';
    var priHauteSousPlancher = FEATURES.filter(function(r){
      return r.priorite === "haute" && r.sante !== null && r.sante !== undefined && r.sante < CI_FLOOR_HAUTE;
    }).length;
    html += '<div class="tile pri-hi"><div class="n tabular">' + priHauteSousPlancher +
      '</div><div class="l">Priorité haute sous le plancher (' + CI_FLOOR_HAUTE + ')</div></div>';
    // REV-180 : combien de priorités affichées n'ont jamais été revues
    // manuellement (amorçage automatique, cf. isReviewedPrioritySource).
    var priorEncoreAmorcees = FEATURES.filter(function(r){
      return !isReviewedPrioritySource(r.priorite_source);
    }).length;
    html += '<div class="tile unreviewed"><div class="n tabular">' + priorEncoreAmorcees +
      '</div><div class="l">Priorités encore amorcées (jamais revues manuellement)</div></div>';
    document.getElementById("tiles").innerHTML = html;
  }

  /* ==================================================================
     3. grille par domaine (clic = filtre)
     ================================================================== */
  var DOMAINS = Array.from(new Set(FEATURES.map(function(r){ return r.domaine; }))).sort();

  function renderFamGrid(){
    var counts = {};
    DOMAINS.forEach(function(d){ counts[d] = { low:0, mid:0, good:0, great:0, na:0, total:0 }; });
    FEATURES.forEach(function(r){
      var lvl = healthLevel(r.sante);
      counts[r.domaine][lvl]++;
      counts[r.domaine].total++;
    });
    var html = DOMAINS.map(function(d){
      var c = counts[d];
      var bars = HEALTH_BRACKET_ORDER.map(function(k){
        if (!c[k]) return "";
        var pct = c[k] / c.total * 100;
        return '<span style="width:' + pct.toFixed(2) + '%;background:' + healthColor(k) + '" title="' +
               HEALTH_BRACKET_LABEL[k] + " " + c[k] + '"></span>';
      }).join("");
      return '<button type="button" class="fam-row" data-dom="' + esc(d) + '">' +
             '<span class="fname">' + esc(d) + '</span>' +
             '<span class="fbar">' + bars + '</span>' +
             '<span class="ftotal tabular">' + c.total + '</span>' +
             '</button>';
    }).join("");
    document.getElementById("famGrid").innerHTML = html;
    document.getElementById("famGrid").addEventListener("click", function(e){
      var btn = e.target.closest(".fam-row");
      if (!btn) return;
      var d = btn.getAttribute("data-dom");
      state.domaines = (state.domaines.size === 1 && state.domaines.has(d)) ? new Set() : new Set([d]);
      syncChips();
      render();
    });
  }

  /* ---------- filter / sort state (table principale) ---------- */
  var state = {
    q: "",
    domaines: new Set(),
    priorites: new Set(),
    sante: new Set(),
    sortKey: "rang",
    sortDir: -1,
    expanded: new Set()
  };

  function renderChips(){
    var priWrap = document.getElementById("priChips");
    PRIORITY_ORDER.forEach(function(p){
      var n = FEATURES.filter(function(r){ return r.priorite === p; }).length;
      var chip = document.createElement("button");
      chip.type = "button"; chip.className = "chip pri";
      chip.setAttribute("aria-pressed", "false");
      chip.dataset.kind = "priorite"; chip.dataset.val = p;
      chip.innerHTML = esc(p) + ' <span class="c tabular">' + n + "</span>";
      priWrap.appendChild(chip);
    });
    var healthWrap = document.getElementById("healthChips");
    HEALTH_BRACKET_ORDER.forEach(function(k){
      var n = globalBuckets[k];
      var chip = document.createElement("button");
      chip.type = "button"; chip.className = "chip";
      chip.setAttribute("aria-pressed", "false");
      chip.dataset.kind = "sante"; chip.dataset.val = k;
      chip.innerHTML = HEALTH_BRACKET_LABEL[k] + ' <span class="c tabular">' + n + "</span>";
      healthWrap.appendChild(chip);
    });
    var domWrap = document.getElementById("domChips");
    DOMAINS.forEach(function(d){
      var n = FEATURES.filter(function(r){ return r.domaine === d; }).length;
      var chip = document.createElement("button");
      chip.type = "button"; chip.className = "chip";
      chip.setAttribute("aria-pressed", "false");
      chip.dataset.kind = "domaine"; chip.dataset.val = d;
      chip.innerHTML = esc(d) + ' <span class="c tabular">' + n + "</span>";
      domWrap.appendChild(chip);
    });
    document.querySelector("#panel-bilan .chip-groups").addEventListener("click", function(e){
      var chip = e.target.closest(".chip");
      if (!chip) return;
      var kind = chip.dataset.kind, val = chip.dataset.val;
      var set = kind === "priorite" ? state.priorites : (kind === "sante" ? state.sante : state.domaines);
      if (set.has(val)) set.delete(val); else set.add(val);
      syncChips();
      render();
    });
  }

  function syncChips(){
    document.querySelectorAll("#panel-bilan .chip[data-kind]").forEach(function(chip){
      var kind = chip.dataset.kind, val = chip.dataset.val;
      var set = kind === "priorite" ? state.priorites : (kind === "sante" ? state.sante : state.domaines);
      chip.setAttribute("aria-pressed", set.has(val) ? "true" : "false");
    });
  }

  /* ==================================================================
     4. table principale — recherche, filtres, tri par colonne
     ================================================================== */
  function matches(r, q){
    if (!q) return true;
    var hay = (r.fonctionnalite + " " + r.domaine + " " + r.id + " " + r.priorite + " " +
               r.preuve.join(" ")).toLowerCase();
    return hay.indexOf(q) !== -1;
  }

  function filteredRows(){
    var q = state.q.trim().toLowerCase();
    return FEATURES.filter(function(r){
      if (state.domaines.size && !state.domaines.has(r.domaine)) return false;
      if (state.priorites.size && !state.priorites.has(r.priorite)) return false;
      if (state.sante.size && !state.sante.has(healthLevel(r.sante))) return false;
      if (!matches(r, q)) return false;
      return true;
    });
  }

  function sortValue(r, key){
    if (key === "fonctionnalite") return r.fonctionnalite.toLowerCase();
    if (key === "sante") return (r.sante === null || r.sante === undefined) ? -1 : r.sante;
    if (key === "delta") return (r.delta === null || r.delta === undefined) ? 0 : r.delta;
    if (key === "priorite") return PRIORITY_ORDER.indexOf(r.priorite);
    if (key === "rang") return r.rang;
    if (SUBSCORE_KEYS.indexOf(key) !== -1) {
      var v = r.sous_scores[key].valeur;
      return (v === null || v === undefined) ? -1 : v;
    }
    return r[key];
  }

  function sortRows(rows){
    var key = state.sortKey, dir = state.sortDir;
    var copy = rows.slice();
    copy.sort(function(a, b){
      var av = sortValue(a, key), bv = sortValue(b, key);
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return a._idx - b._idx;
    });
    return copy;
  }

  function proofCell(r){
    var parts = r.preuve || [];
    var first = parts[0] || "";
    var extra = parts.length - 1;
    return '<span class="line">' + esc(first) + '</span>' +
           (extra > 0 ? '<span class="more">+' + extra + ' référence' + (extra > 1 ? "s" : "") + '</span>' : "");
  }

  function rowHtml(r){
    var expanded = state.expanded.has(r.id);
    var out = '<tr class="row' + (expanded ? " expanded" : "") + '" data-id="' + esc(r.id) + '">' +
      '<td class="cell-toggle"><button class="toggle-btn" type="button" aria-expanded="' + expanded +
        '" aria-controls="detail-' + esc(r.id) + '" data-toggle="' + esc(r.id) + '">&#9656;</button></td>' +
      '<td class="cell-feat">' +
        '<div class="name">' + esc(r.fonctionnalite) + '</div>' +
        '<div class="domaine">' + esc(r.domaine) + ' &middot; <span class="id-tag mono">' + esc(r.id) + '</span></div>' +
      '</td>' +
      '<td>' + healthBadge(r.sante) + '</td>' +
      '<td>' + deltaCell(r.delta) + '</td>' +
      '<td>' + priorityBadge(r.priorite, r.priorite_source) + '</td>' +
      '<td>' + subCell(r.sous_scores.tests) + '</td>' +
      '<td>' + subCell(r.sous_scores.atteignabilite) + '</td>' +
      '<td>' + subCell(r.sous_scores.garde) + '</td>' +
      '<td>' + subCell(r.sous_scores.dette) + '</td>' +
      '<td class="cell-proof">' + proofCell(r) + '</td>' +
      '</tr>';
    out += '<tr class="detail-row" id="detail-' + esc(r.id) + '"' + (expanded ? "" : " hidden") +
      '><td colspan="10">' + (expanded ? detailHtml(r) : "") + '</td></tr>';
    return out;
  }

  function subscoreRow(name, score){
    var value = score ? score.valeur : null;
    var hasValue = value !== null && value !== undefined;
    var pct = hasValue ? value : 0;
    var color = hasValue ? healthColor(healthLevel(value)) : "var(--ink-3)";
    var valueText = hasValue ? value.toFixed(1) : "n/a";
    var evidence = (score && score.preuve) || {};
    var evKeys = Object.keys(evidence);
    var evHtml = evKeys.length
      ? '<ul class="test-list" style="grid-column:1 / -1;margin-top:2px">' +
        evKeys.map(function(k){
          return '<li><code>' + esc(k) + '</code> — ' + esc(String(evidence[k])) + '</li>';
        }).join("") + '</ul>'
      : '<ul class="test-list" style="grid-column:1 / -1;margin-top:2px">' +
        '<li style="color:var(--ink-3)">aucune preuve — sous-score non applicable</li></ul>';
    return '<div class="crit-row"><span>' + esc(SUBSCORE_LABEL[name]) + '</span>' +
      '<span class="cval tabular">' + valueText + '</span>' +
      '<span class="cbar"><span style="width:' + pct + '%;background:' + color + '"></span></span></div>' + evHtml;
  }

  function listBlock(label, items){
    if (!items || !items.length) {
      return '<p><b>' + esc(label) + '</b> : aucun</p>';
    }
    return '<p><b>' + esc(label) + '</b></p><ul class="test-list">' +
      items.map(function(i){ return '<li><code>' + esc(i) + '</code></li>'; }).join("") + '</ul>';
  }

  function qualiteBlock(q){
    var typage = q.typage_strict === null || q.typage_strict === undefined
      ? "non applicable (aucune preuve dans core/app/)"
      : (q.typage_strict ? "oui" : "non");
    var parts = [
      '<p><b>Typage strict (mypy --strict)</b> : ' + esc(typage) + "</p>",
      listBlock("Exemptions de couches (lint-imports)", q.exemptions_de_couches),
      listBlock("eslint-disable", q.eslint_disable),
      listBlock("Échappatoires de typage (@ts-expect-error, : any)", q.echappatoires_de_typage)
    ];
    return '<div class="block suggestion"><h4>Reprise qualité — faits, sans note</h4>' + parts.join("") + "</div>";
  }

  function detailHtml(r){
    var subs = SUBSCORE_KEYS.map(function(k){ return subscoreRow(k, r.sous_scores[k]); }).join("");
    var blocks = [];
    blocks.push(
      '<div class="block crits"><h4>Sous-scores (santé calculée, jamais moyennée avec la priorité)</h4>' +
      '<div class="crit-grid">' + subs + "</div></div>"
    );
    blocks.push(qualiteBlock(r.qualite));
    if (r.preuve && r.preuve.length) {
      blocks.push(
        '<div class="block proof"><h4>Preuve</h4><ul class="test-list">' +
        r.preuve.map(function(p){ return '<li><code>' + esc(p) + '</code></li>'; }).join("") + '</ul></div>'
      );
    }
    return '<div class="detail">' + blocks.join("") + "</div>";
  }

  function render(){
    var rows = sortRows(filteredRows());
    document.getElementById("resultCount").textContent = rows.length + " / " + total + " affichées";
    var tbody = document.getElementById("tbody");
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="10"><div class="empty-state">' +
        '<div class="big">Aucune fonctionnalité ne correspond</div>' +
        "Essayez d'élargir la recherche ou de retirer un filtre.</div></td></tr>";
      updateSortIndicators();
      return;
    }
    tbody.innerHTML = rows.map(rowHtml).join("");
    updateSortIndicators();
  }

  function updateSortIndicators(){
    document.querySelectorAll('#panel-bilan th[data-sort] .arrow').forEach(function(a){ a.textContent = ""; });
    if (state.sortKey) {
      var th = document.querySelector('#panel-bilan th[data-sort="' + state.sortKey + '"] .arrow');
      if (th) th.textContent = state.sortDir === 1 ? "↑" : "↓";
    }
  }

  document.getElementById("tbody").addEventListener("click", function(e){
    var btn = e.target.closest(".toggle-btn");
    if (!btn) return;
    var id = btn.dataset.toggle;
    if (state.expanded.has(id)) state.expanded.delete(id); else state.expanded.add(id);
    render();
  });

  document.querySelectorAll('#panel-bilan th[data-sort] button').forEach(function(btn){
    btn.addEventListener("click", function(){
      var key = btn.closest("th").dataset.sort;
      if (state.sortKey === key) { state.sortDir *= -1; }
      else { state.sortKey = key; state.sortDir = 1; }
      render();
    });
  });

  document.getElementById("searchInput").addEventListener("input", function(e){
    state.q = e.target.value;
    render();
  });

  document.getElementById("resetBtn").addEventListener("click", function(){
    state.q = ""; state.domaines = new Set(); state.priorites = new Set(); state.sante = new Set();
    state.sortKey = "rang"; state.sortDir = -1;
    document.getElementById("searchInput").value = "";
    syncChips();
    render();
  });

  /* ==================================================================
     tabs
     ================================================================== */
  document.querySelectorAll(".tab-btn").forEach(function(btn){
    btn.addEventListener("click", function(){
      var tab = btn.dataset.tab;
      document.querySelectorAll(".tab-btn").forEach(function(b){
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
      });
      document.getElementById("panel-bilan").hidden = tab !== "bilan";
      document.getElementById("panel-evolution").hidden = tab !== "evolution";
    });
  });

  /* ==================================================================
     6. onglet Évolution — amélioré / dégradé depuis l'instantané précédent
     ================================================================== */
  function evolutionRow(r){
    return '<tr class="row"><td class="cell-feat"><div class="name">' + esc(r.fonctionnalite) + '</div></td>' +
      '<td class="mono">' + esc(r.domaine) + '</td><td>' + deltaCell(r.delta) + '</td></tr>';
  }

  function renderEvolution(){
    var withDelta = FEATURES.filter(function(r){ return r.delta !== null && r.delta !== undefined; });
    var improved = withDelta.filter(function(r){ return r.delta >= 0.05; })
      .sort(function(a, b){ return b.delta - a.delta; });
    var degraded = withDelta.filter(function(r){ return r.delta <= -0.05; })
      .sort(function(a, b){ return a.delta - b.delta; });

    var medianText = (DATA.sante_mediane === null || DATA.sante_mediane === undefined)
      ? "—" : DATA.sante_mediane.toFixed(1);

    document.getElementById("tilesEvolution").innerHTML =
      '<div class="tile total"><div class="n tabular">' + medianText + '</div><div class="l">Santé médiane courante</div></div>' +
      '<div class="tile"><div class="n tabular">' + improved.length + '</div><div class="l">Améliorées</div></div>' +
      '<div class="tile"><div class="n tabular">' + degraded.length + '</div><div class="l">Dégradées</div></div>' +
      '<div class="tile"><div class="n tabular">' + withDelta.length + '</div><div class="l">Comparables à l\'instantané précédent</div></div>';

    document.getElementById("tbodyImproved").innerHTML = improved.length
      ? improved.map(evolutionRow).join("")
      : '<tr><td colspan="3"><div class="empty-state">Aucune fonctionnalité améliorée depuis le dernier instantané.</div></td></tr>';
    document.getElementById("tbodyDegraded").innerHTML = degraded.length
      ? degraded.map(evolutionRow).join("")
      : '<tr><td colspan="3"><div class="empty-state">Aucune fonctionnalité dégradée depuis le dernier instantané.</div></td></tr>';
  }

  /* ==================================================================
     init
     ================================================================== */
  document.getElementById("genDate").textContent = DATA.date || "";
  document.getElementById("genCommit").textContent = (DATA.commit || "").slice(0, 12);
  document.getElementById("tabCountBilan").textContent = total;

  renderStackBar();
  renderTiles();
  renderFamGrid();
  renderChips();
  render();
  renderEvolution();
})();
