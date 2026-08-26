// Passages in een antwoord aanwijzen die de brongetrouwheidscontrole afkeurde.
//
// graph-qa levert per beurt `grounding.niet_letterlijk`: tekst die het antwoord als citaat
// presenteert maar die niet letterlijk in de opgehaalde wettekst staat. Dat stond alleen in een blok
// ónder het antwoord — een waarschuwing die je makkelijk overslaat, terwijl je in de tekst zelf naar
// een citaat kijkt dat er betrouwbaar uitziet omdat het aanhalingstekens draagt. Juist bij een
// platform dat om brongetrouwheid draait hoort die twijfel te staan wáár je leest.
//
// Pure functie omdat vitest node-env draait zonder DOM (zie `lib/selectie.ts`); het component doet
// alleen de weergave.

export interface Segment {
  tekst: string;
  /** Hoort dit stuk als afgekeurd citaat te worden gemarkeerd? */
  gemarkeerd: boolean;
}

/** Knip `tekst` op in stukken, waarbij elk voorkomen van een passage apart komt te staan.
 *
 *  Matcht letterlijk (geen normalisatie): wijkt de weergave af van wat de controle vergeleek, dan
 *  markeren we liever niets dan het verkeerde stuk — het blok onder het antwoord noemt de passage
 *  dan nog steeds. De langste passage wint, zodat een kort fragment dat toevallig in een langer
 *  fragment zit dat langere niet doormidden knipt.
 */
export function splitsOpPassages(tekst: string, passages: readonly string[]): Segment[] {
  const zoek = [...new Set(passages.filter((p) => p.trim().length > 0))].sort(
    (a, b) => b.length - a.length,
  );
  if (!tekst || zoek.length === 0) return tekst ? [{ tekst, gemarkeerd: false }] : [];

  const uit: Segment[] = [];
  let rest = tekst;
  while (rest) {
    // De vroegste treffer wint; bij gelijke positie de langste (die staat vooraan in `zoek`).
    let besteIndex = -1;
    let bestePassage = "";
    for (const p of zoek) {
      const i = rest.indexOf(p);
      if (i === -1) continue;
      if (besteIndex === -1 || i < besteIndex) {
        besteIndex = i;
        bestePassage = p;
      }
    }
    if (besteIndex === -1) {
      uit.push({ tekst: rest, gemarkeerd: false });
      break;
    }
    if (besteIndex > 0) uit.push({ tekst: rest.slice(0, besteIndex), gemarkeerd: false });
    uit.push({ tekst: bestePassage, gemarkeerd: true });
    rest = rest.slice(besteIndex + bestePassage.length);
  }
  return uit;
}

/* Minimale hast-typen: react-markdown geeft geen publieke typen voor een eigen rehype-plugin, en een
   losse `@types/hast`-afhankelijkheid is voor deze paar velden niet de moeite. */
export interface HastKnoop {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastKnoop[];
}

/** Rehype-plugin die afgekeurde citaten in de gerenderde tekst aanwijst.
 *
 *  De brongetrouwheidscontrole meldde ze alleen in een blok ónder het antwoord, en dat blok slaat
 *  iedereen op den duur over — terwijl je in de tekst zelf naar een passage kijkt die er betrouwbaar
 *  uitziet omdat er aanhalingstekens omheen staan. Nu staat de twijfel wáár je leest.
 *
 *  Op hast-niveau en niet op de bron-markdown: zo raken we de tekst zelf niet aan (geen ingevoegde
 *  tekens die de gebruiker meekopieert) en blijft de opmaak precies zoals het model hem bedoelde.
 *  Code-blokken slaan we over — daar is een treffer per definitie toeval.
 */
export function markeerPassages(passages: readonly string[]) {
  return () => (boom: HastKnoop) => {
    const loop = (knoop: HastKnoop): void => {
      if (!knoop.children?.length) return;
      if (knoop.tagName === "code" || knoop.tagName === "pre") return;
      const nieuw: HastKnoop[] = [];
      for (const kind of knoop.children) {
        if (kind.type !== "text" || !kind.value) {
          loop(kind);
          nieuw.push(kind);
          continue;
        }
        const delen = splitsOpPassages(kind.value, passages);
        if (!delen.some((d) => d.gemarkeerd)) {
          nieuw.push(kind);
          continue;
        }
        for (const deel of delen) {
          nieuw.push(
            deel.gemarkeerd
              ? {
                  type: "element",
                  tagName: "mark",
                  properties: { title: "Dit citaat staat niet letterlijk in de opgehaalde tekst." },
                  children: [{ type: "text", value: deel.tekst }],
                }
              : { type: "text", value: deel.tekst },
          );
        }
      }
      knoop.children = nieuw;
    };
    loop(boom);
  };
}
