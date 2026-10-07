#!/bin/sh
# usage: count-backlog-etat.sh docs/revue/2026-09-04-backlog.md [lists]
awk -v lists="$2" '
/^### REV-/{id=$2}
/^- \*\*État :?\*?\*? ?/ && id!=""{
  s=$0; sub(/^- \*\*État :?\*?\*? */,"",s); gsub(/\*/,"",s); s=tolower(s)
  if(s ~ /^partiel/) k="partiel"
  else if(s ~ /^ferm|^résolu/) k="ferme"
  else if(s ~ /^ouvert/) k="ouvert"
  else if(s ~ /^observation|^informationnel/) k="observation"
  else k="AUTRE"
  n[k]++; tot++; l[k]=l[k] (l[k]==""?"":", ") id; id=""
}
END{ if(lists!="") {for(k in l) print k": "l[k]} else {for(k in n) print k"\t"n[k]; print "total\t"tot} }' "$1" | sort
