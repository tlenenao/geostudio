// SPDX-License-Identifier: Apache-2.0
import { useEffect } from "react";

/** Titre/description/canonical dynamiques (SP-55 §3.4, GAP-07) — complète
 * (ne remplace pas) le chemin robot rendu côté serveur (Tâches 7/8) : utile
 * pour l'onglet navigateur d'un humain et pour Googlebot, qui exécute le JS
 * avant indexation, contrairement aux robots de prévisualisation de
 * messagerie (Slack/Twitter/…) visés par le routage Traefik seo-bots.
 *
 * Upserte les balises existantes plutôt que d'en poser une seconde (un
 * re-rendu avec un nouveau titre/description ne doit pas dupliquer
 * `<meta name="description">`), et les retire au démontage : une SPA qui
 * quitte /sites/{slug} pour une autre page ne doit pas laisser une
 * description/canonical périmée dans le <head>. */
export function useDocumentMeta({
  title,
  description,
  canonicalUrl,
}: {
  title: string;
  description: string;
  canonicalUrl: string;
}) {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = title;

    let meta = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    const createdMeta = meta === null;
    if (!meta) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "description");
      document.head.appendChild(meta);
    }
    meta.setAttribute("content", description);

    let link = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    const createdLink = link === null;
    if (!link) {
      link = document.createElement("link");
      link.setAttribute("rel", "canonical");
      document.head.appendChild(link);
    }
    link.setAttribute("href", canonicalUrl);

    return () => {
      document.title = previousTitle;
      if (createdMeta) meta.remove();
      if (createdLink) link.remove();
    };
  }, [title, description, canonicalUrl]);
}
