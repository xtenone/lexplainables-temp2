import { describe, expect, it } from "vitest";
import {
  bronVan,
  eigenMarkeringenVoorContext,
  documentStatusLabel,
  regelsVan,
  pastInFilter,
  sorteerReview,
  volgendeElement,
  vraagContextLabel,
  vraagContextVan,
  vraagSuggesties,
  overlaptSelectie,
  doelVanKandidaat,
  kandidaatLabel,
  kandidaatPrompt,
  kandidatenAlsTekst,
  mergeVoorstellen,
  annotatieTitel,
  isVerwijderd,
  isBeslist,
  isVergrendeld,
  isDocumentVergrendeld,
  alGemarkeerd,
} from "./annotatie";
import type { AnnotatieDocument, AnnotatieElement, GraafArtikel, VoorstelElement } from "./types";

describe("documentStatusLabel", () => {
  it("mapt de drie documentstatussen naar NL-labels", () => {
    expect(documentStatusLabel("in_review")).toBe("In behandeling");
    expect(documentStatusLabel("geaccordeerd")).toBe("Geaccordeerd");
    expect(documentStatusLabel("gepromoveerd")).toBe("In de graaf");
  });
});

function voorstel(over: Partial<VoorstelElement> = {}): VoorstelElement {
  return {
    klasse: "Voorwaarde",
    tekst: "indien betaling uitblijft",
    lid: "1",
    toelichting: "",
    vindplaats: "",
    alternatieven: [],
    grounded: true,
    ...over,
  };
}

// De agent stuurt hetzelfde element opnieuw zodra de Critic om een herziening vraagt. Zonder
// ontdubbelen zou de werkplek dubbele kaarten tonen én dubbel naar de server sturen.
describe("mergeVoorstellen", () => {
  it("voegt een onbekend element toe", () => {
    const uit = mergeVoorstellen([], voorstel({ id: "a1" }));
    expect(uit).toHaveLength(1);
  });

  it("vervangt op id — de laatste ronde wint", () => {
    const eerst = mergeVoorstellen([], voorstel({ id: "a1", klasse: "Rechtsfeit" }));
    const na = mergeVoorstellen(eerst, voorstel({ id: "a1", klasse: "Voorwaarde", aandacht: "groen" }));
    expect(na).toHaveLength(1);
    expect(na[0].klasse).toBe("Voorwaarde");
    expect(na[0].aandacht).toBe("groen");
  });

  it("houdt verschillende id's uit elkaar", () => {
    let uit = mergeVoorstellen([], voorstel({ id: "a1" }));
    uit = mergeVoorstellen(uit, voorstel({ id: "a2", tekst: "de ontvanger" }));
    expect(uit).toHaveLength(2);
  });

  it("valt zonder id terug op tekst en lid, net als de server", () => {
    const eerst = mergeVoorstellen([], voorstel({ toelichting: "eerste" }));
    // Zelfde tekst (andere spatiëring/kapitalisatie) en lid → hetzelfde element.
    const na = mergeVoorstellen(eerst, voorstel({ tekst: "Indien  betaling   uitblijft", toelichting: "beter" }));
    expect(na).toHaveLength(1);
    expect(na[0].toelichting).toBe("beter");
  });

  it("houdt een herclassificatie op hetzelfde element — de klasse telt niet mee", () => {
    // Regressie: telde de klasse mee in de sleutel, dan werd een herziening die alleen
    // herclassificeerde een tweede kaart naast het origineel. Zowel mét id als zonder.
    const metId = mergeVoorstellen(
      [],
      voorstel({ id: "a1", klasse: "Rechtsobject" }),
    );
    expect(mergeVoorstellen(metId, voorstel({ id: "a1", klasse: "Voorwaarde" }))).toHaveLength(1);

    const zonderId = mergeVoorstellen([], voorstel({ klasse: "Rechtsobject" }));
    const na = mergeVoorstellen(zonderId, voorstel({ klasse: "Voorwaarde" }));
    expect(na).toHaveLength(1);
    expect(na[0].klasse).toBe("Voorwaarde");
  });

  it("ziet hetzelfde fragment in een ander lid als een apart element", () => {
    const eerst = mergeVoorstellen([], voorstel({ lid: "1" }));
    const na = mergeVoorstellen(eerst, voorstel({ lid: "2" }));
    expect(na).toHaveLength(2);
  });

  it("laat een element met id ongemoeid bij een naamloos voorstel met dezelfde tekst", () => {
    // Een voorstel mét id en één zonder zijn niet zomaar hetzelfde: het id is leidend.
    const eerst = mergeVoorstellen([], voorstel({ id: "a1" }));
    const na = mergeVoorstellen(eerst, voorstel({}));
    expect(na).toHaveLength(2);
  });
});

describe("kandidaten bij een onderwerp-vraag", () => {
  const k = { bwbId: "BWBR0004770", artikel: "36a", lid: "1", citeertitel: "Invorderingswet 1990" };

  it("noemt lid alleen als er een lid is", () => {
    expect(kandidaatLabel(k)).toBe("Artikel 36a, lid 1 — Invorderingswet 1990");
    expect(kandidaatLabel({ bwbId: "BWBR1", artikel: "36" })).toBe("Artikel 36");
  });

  it("zet het bwbId in de vervolgopdracht", () => {
    // Zonder bwbId moet de ophaal-agent opnieuw zoeken op de citeertitel — en kan hij bij een
    // andere bepaling uitkomen dan die de jurist aanwees.
    expect(kandidaatPrompt(k)).toContain("BWBR0004770");
    expect(kandidaatPrompt(k)).toContain("artikel 36a lid 1");
  });

  it("levert de keuze ook als gestructureerd doel", () => {
    // Hiermee slaat de agent de supervisor en de ophaal-agent over — en kan hij niet bij een
    // andere bepaling uitkomen dan de jurist zojuist aanwees.
    expect(doelVanKandidaat(k)).toEqual({
      bwbId: "BWBR0004770",
      artikel: "36a",
      lid: "1",
      citeertitel: "Invorderingswet 1990",
    });
  });

  it("laat lege velden weg uit het doel", () => {
    expect(doelVanKandidaat({ bwbId: "BWBR1", artikel: "36" })).toEqual({
      bwbId: "BWBR1",
      artikel: "36",
    });
  });

  it("bewaart de keuze leesbaar voor na een herlaadbeurt", () => {
    const tekst = kandidatenAlsTekst("Ik vond 2 bepalingen.", [k, { bwbId: "BWBR1", artikel: "36" }]);
    expect(tekst.split("\n")).toHaveLength(3);
    expect(tekst).toContain("- Artikel 36a, lid 1 — Invorderingswet 1990");
  });
});

// --- de reden hoeft niet meer gevraagd te worden ------------------------------------------------

const ELEMENT = {
  id: "el-1",
  klasse: "Rechtsobject",
  tekst: "belastingaanslag",
  lid: "1",
  toelichting: "het object",
  vindplaats: "",
  herkomst: "agent",
  gewijzigd_door: "",
  lifecycle: "voorgesteld",
  alternatieven: [],
  aandacht: null,
  critic: "",
  critic_rondes: [],
  critic_suggestie: null,
  anker: null,
  diff: {},
  beslissingen: [],
} as unknown as AnnotatieElement;

describe("overlaptSelectie", () => {
  const bereik = { start: 10, eind: 26 };

  it("herkent een selectie die het fragment raakt", () => {
    expect(overlaptSelectie({ start: 6, eind: 26 }, bereik)).toBe(true);   // uitbreiden naar links
    expect(overlaptSelectie({ start: 10, eind: 20 }, bereik)).toBe(true);  // inkorten
    expect(overlaptSelectie({ start: 26, eind: 40 }, bereik)).toBe(true);  // sluit erop aan
  });

  it("herkent een selectie die er los van staat", () => {
    expect(overlaptSelectie({ start: 0, eind: 9 }, bereik)).toBe(false);
    expect(overlaptSelectie({ start: 27, eind: 40 }, bereik)).toBe(false);
  });
});

// --- de lijst ordenen -----------------------------------------------------------------------------

function el(id: string, extra: Partial<AnnotatieElement> = {}): AnnotatieElement {
  return { ...ELEMENT, id, ...extra } as AnnotatieElement;
}

describe("sorteerReview", () => {
  it("volgt de canonieke JAS-tabelvolgorde, niet de invoervolgorde", () => {
    const lijst = [
      el("vw", { klasse: "Voorwaarde" }),
      el("subj", { klasse: "Rechtssubject" }),
      el("feit", { klasse: "Rechtsfeit" }),
      el("obj", { klasse: "Rechtsobject" }),
    ];
    expect(sorteerReview(lijst).map((e) => e.id)).toEqual(["subj", "obj", "feit", "vw"]);
  });

  it("zet een onbekende klasse achteraan", () => {
    const lijst = [el("x", { klasse: "Iets Onbekends" }), el("subj", { klasse: "Rechtssubject" })];
    expect(sorteerReview(lijst).map((e) => e.id)).toEqual(["subj", "x"]);
  });

  it("sorteert het lid numeriek, niet lexicaal", () => {
    // "10" < "2" als je op tekst sorteert; dat is precies de val.
    const lijst = [
      el("tien", { klasse: "Rechtsobject", lid: "10" }),
      el("twee", { klasse: "Rechtsobject", lid: "2" }),
      el("geen", { klasse: "Rechtsobject", lid: "" }),
    ];
    expect(sorteerReview(lijst).map((e) => e.id)).toEqual(["geen", "twee", "tien"]);
  });

  it("sorteert binnen een klasse op de plek in de tekst", () => {
    const lijst = [el("laat", { klasse: "Rechtsobject" }), el("vroeg", { klasse: "Rechtsobject" })];
    const posities = new Map([["laat", 80], ["vroeg", 10]]);
    expect(sorteerReview(lijst, posities).map((e) => e.id)).toEqual(["vroeg", "laat"]);
  });

  it("zet een markering die niet in de tekst te vinden is achteraan binnen zijn klasse", () => {
    const lijst = [
      el("zwevend", { klasse: "Rechtsobject" }),
      el("gevonden", { klasse: "Rechtsobject" }),
      el("later", { klasse: "Voorwaarde" }),
    ];
    const posities = new Map([["gevonden", 10], ["later", 5]]);
    // "zwevend" heeft geen positie: achteraan bij de Rechtsobjecten, maar nog wél vóór de Voorwaarde.
    expect(sorteerReview(lijst, posities).map((e) => e.id)).toEqual(["gevonden", "zwevend", "later"]);
  });

  it("verandert NIET als een element wordt beoordeeld", () => {
    // Dit is het hele punt: eerder sprong een goedgekeurd element naar achteren en schoof de rest op.
    const voor = [
      el("a", { klasse: "Rechtssubject", aandacht: "groen" }),
      el("b", { klasse: "Rechtsobject", aandacht: "rood" }),
      el("c", { klasse: "Rechtsfeit" }),
    ];
    const na = [
      el("a", { klasse: "Rechtssubject", aandacht: "groen", lifecycle: "human_approved" }),
      el("b", { klasse: "Rechtsobject", aandacht: "rood" }),
      el("c", { klasse: "Rechtsfeit", lifecycle: "rejected" }),
    ];
    expect(sorteerReview(na).map((e) => e.id)).toEqual(sorteerReview(voor).map((e) => e.id));
  });

  it("is stabiel bij een volledig gelijke sleutel", () => {
    const lijst = [el("1"), el("2"), el("3")];
    expect(sorteerReview(lijst).map((e) => e.id)).toEqual(["1", "2", "3"]);
  });

  it("werkt zonder positiekaart", () => {
    const lijst = [el("vw", { klasse: "Voorwaarde" }), el("subj", { klasse: "Rechtssubject" })];
    expect(sorteerReview(lijst).map((e) => e.id)).toEqual(["subj", "vw"]);
  });

  it("laat de invoer ongemoeid", () => {
    const lijst = [el("a", { klasse: "Voorwaarde" }), el("b", { klasse: "Rechtssubject" })];
    sorteerReview(lijst);
    expect(lijst.map((e) => e.id)).toEqual(["a", "b"]);
  });
});

describe("pastInFilter", () => {
  it("filtert op te beoordelen", () => {
    expect(pastInFilter(el("a"), "te_beoordelen")).toBe(true);
    expect(pastInFilter(el("b", { lifecycle: "human_approved" }), "te_beoordelen")).toBe(false);
  });

  it("filtert op aandacht — groen telt niet mee", () => {
    expect(pastInFilter(el("r", { aandacht: "rood" }), "aandacht")).toBe(true);
    expect(pastInFilter(el("g", { aandacht: "groen" }), "aandacht")).toBe(false);
    expect(pastInFilter(el("x"), "aandacht")).toBe(false);
  });

  it("laat bij 'alles' alles door", () => {
    expect(pastInFilter(el("b", { lifecycle: "rejected" }), "alles")).toBe(true);
  });
});

describe("isVergrendeld", () => {
  // Een eindoordeel zet het element op slot; wijzigen kan pas na een expliciete heropening. Bewust
  // een ander begrip dan `isBeslist`, dat de filters en de telling stuurt.
  it("vergrendelt een goedgekeurd en een verworpen element", () => {
    expect(isVergrendeld(el("a", { lifecycle: "human_approved" }))).toBe(true);
    expect(isVergrendeld(el("b", { lifecycle: "rejected" }))).toBe(true);
  });

  it("laat een aangepast element bewerkbaar", () => {
    // Klasse wijzigen en er daarna een toelichting bij typen is één doorlopende handeling; een slot
    // na de eerste wijziging zou daar een heropening tussen wringen.
    const bewerkt = el("c", { lifecycle: "edited" });
    expect(isBeslist(bewerkt)).toBe(true);
    expect(isVergrendeld(bewerkt)).toBe(false);
  });

  it("laat een onbeoordeeld element met rust", () => {
    expect(isVergrendeld(el("d"))).toBe(false);
    expect(isVergrendeld(el("e", { lifecycle: "critic_checked" }))).toBe(false);
  });

  it("vergrendelt een eigen markering niet", () => {
    // Die staat bij het aanmaken al op `human_approved`: gemaakt, niet beoordeeld. Op slot zetten
    // zou je eigen verse markering meteen onbewerkbaar maken, wisknop en al.
    expect(isVergrendeld(el("eigen", { lifecycle: "human_approved", herkomst: "mens" }))).toBe(false);
  });
});

describe("alGemarkeerd", () => {
  const items = [
    el("a", { klasse: "Rechtsfeit", tekst: "zes weken na de dagtekening" }),
  ];

  it("herkent een fragment dat er al ligt, ongeacht spaties en kapitalen", () => {
    expect(alGemarkeerd(items, "Rechtsfeit", "  Zes   weken na de dagtekening ")).toBe(true);
  });

  it("telt een verworpen markering NIET mee", () => {
    // Je hebt hem net weggestuurd; "inmiddels gemarkeerd" is dan het omgekeerde van wat er gebeurde,
    // en het ontbrekend-item bleef onaanklikbaar staan terwijl je hem opnieuw wilde toevoegen.
    const verworpen = [el("a", {
      klasse: "Rechtsfeit", tekst: "zes weken na de dagtekening", lifecycle: "rejected",
    })];
    expect(alGemarkeerd(verworpen, "Rechtsfeit", "zes weken na de dagtekening")).toBe(false);
  });

  it("kijkt naar klasse én fragment, en negeert een leeg fragment", () => {
    expect(alGemarkeerd(items, "Rechtssubject", "zes weken na de dagtekening")).toBe(false);
    expect(alGemarkeerd(items, "Rechtsfeit", "   ")).toBe(false);
  });
});

describe("isDocumentVergrendeld", () => {
  it("bevriest alleen een afgerond document", () => {
    expect(isDocumentVergrendeld({ status: "geaccordeerd" })).toBe(true);
    expect(isDocumentVergrendeld({ status: "in_review" })).toBe(false);
    expect(isDocumentVergrendeld({ status: "gepromoveerd" })).toBe(false);
  });
});

describe("volgendeElement", () => {
  const lijst = [el("1"), el("2", { lifecycle: "human_approved" }), el("3")];

  it("loopt vooruit en achteruit door de lijst", () => {
    expect(volgendeElement(lijst, "1")?.id).toBe("2");
    expect(volgendeElement(lijst, "2", -1)?.id).toBe("1");
  });

  it("stopt aan het eind in plaats van rond te lopen", () => {
    // Rondlopen laat je onbedoeld een tweede ronde beginnen zonder dat je het doorhebt.
    expect(volgendeElement(lijst, "3")).toBeUndefined();
    expect(volgendeElement(lijst, "1", -1)).toBeUndefined();
  });

  it("begint bij de rand als er niets geselecteerd is", () => {
    expect(volgendeElement(lijst, undefined)?.id).toBe("1");
    expect(volgendeElement(lijst, undefined, -1)?.id).toBe("3");
  });

  it("slaat bij auto-advance de beslist-elementen over", () => {
    expect(volgendeElement(lijst, "1", 1, true)?.id).toBe("3");
  });

  it("geeft niets terug als de lijst leeg is", () => {
    expect(volgendeElement([], undefined)).toBeUndefined();
  });
});

// --- een vraag over één markering -----------------------------------------------------------------

describe("vraagContextVan", () => {
  const doc = {
    slug: "abc", bwbId: "BWBR0004770", artikel: "36", lid: "2", elementen: [],
  } as unknown as AnnotatieDocument;
  const info = {
    bwbId: "BWBR0004770", artikel: "36", citeertitel: "IW 1990", opschrift: "",
    leden_teksten: [{ lid: "1", tekst: "Eerste lid." }, { lid: "2", tekst: "Tweede lid." }],
  };

  it("vult waar de vraag over gaat", () => {
    const ctx = vraagContextVan("abc", doc, info, el("e1", { klasse: "Rechtsobject", tekst: "aanslag", lid: "1" }));
    expect(ctx).toMatchObject({
      slug: "abc", bwbId: "BWBR0004770", artikel: "36", lid: "1",
      element_id: "e1", klasse: "Rechtsobject", fragment: "aanslag",
    });
  });

  it("valt terug op het lid van het document als het element er geen heeft", () => {
    // Bij een artikel zonder leden staat het lid alleen op het document; zonder terugval zou de
    // agent de verkeerde (of geen) bepaling voor zich krijgen.
    const ctx = vraagContextVan("abc", doc, info, el("e2", { lid: "" }));
    expect(ctx.lid).toBe("2");
  });

  it("stuurt de andere markeringen mee, zonder het gevraagde element", () => {
    // Meesturen in plaats van op het gespreksgeheugen leunen: anders verschilt het antwoord op
    // dezelfde vraag per gesprek.
    const metElementen = {
      ...doc,
      elementen: [
        el("e1", { klasse: "Rechtsobject", tekst: "aanslag" }),
        el("e2", { klasse: "Tijdsaanduiding", tekst: "zes weken" }),
        el("e3", { klasse: "Voorwaarde", tekst: "indien", lifecycle: "rejected" }),
      ],
    } as unknown as AnnotatieDocument;

    const ctx = vraagContextVan("abc", metElementen, info, el("e1", { klasse: "Rechtsobject", tekst: "aanslag" }));
    expect(ctx.bestaande_elementen?.map((b) => b.id)).toEqual(["e2"]);
  });

  it("begrenst het aantal meegestuurde markeringen", () => {
    const veel = {
      ...doc,
      elementen: Array.from({ length: 30 }, (_, i) => el(`x${i}`)),
    } as unknown as AnnotatieDocument;
    expect(vraagContextVan("abc", veel, info, el("anders")).bestaande_elementen).toHaveLength(20);
  });

  it("geeft de getoonde artikeltekst als corpus", () => {
    const ctx = vraagContextVan("abc", doc, info, el("e1"));
    expect(ctx.corpus).toBe("Eerste lid.\n\nTweede lid.");
  });
});

describe("vraagContextLabel", () => {
  it("benoemt klasse, fragment en vindplaats", () => {
    // Deze regel wordt ook opgeslagen bij het bericht: de chip is UI-state en reist niet mee.
    const label = vraagContextLabel(el("e1", { klasse: "Voorwaarde", tekst: "indien", lid: "1" }), {
      artikel: "36",
    } as AnnotatieDocument);
    expect(label).toBe("Voorwaarde — “indien” (art. 36 lid 1)");
  });

  it("laat de vindplaats weg als het document onbekend is", () => {
    expect(vraagContextLabel(el("e1", { klasse: "Voorwaarde", tekst: "indien" }))).toBe(
      "Voorwaarde — “indien”",
    );
  });
});

// --- de brontekst en de lidnummers -----------------------------------------------------------------

describe("regelsVan", () => {
  const artikel = (leden: { lid: string; tekst: string }[]): GraafArtikel => ({
    bwbId: "BWBR0004770", artikel: "8", citeertitel: "Invorderingswet 1990", opschrift: "",
    leden_teksten: leden,
  });

  it("houdt het lidnummer bij de regel waarin het staat", () => {
    const regels = regelsVan(artikel([{ lid: "3", tekst: "De ontvanger maant aan." }]));
    expect(regels).toEqual([{ lid: "3", regel: "3. De ontvanger maant aan." }]);
  });

  it("laat het nummer weg bij een artikel zonder genummerde leden", () => {
    expect(regelsVan(artikel([{ lid: "", tekst: "Deze wet berust op…" }]))).toEqual([
      { lid: "", regel: "Deze wet berust op…" },
    ]);
  });

  it("slaat lege leden over", () => {
    const regels = regelsVan(artikel([{ lid: "1", tekst: "Eerste." }, { lid: "2", tekst: "  " }]));
    expect(regels).toEqual([{ lid: "1", regel: "1. Eerste." }]);
  });

  it("levert een bron waarin de offsets van de regels kloppen", () => {
    const regels = regelsVan(artikel([{ lid: "1", tekst: "Eerste." }, { lid: "2", tekst: "Tweede." }]));
    const bron = bronVan(regels);
    expect(bron).toBe("1. Eerste.\n\n2. Tweede.");
    expect(bron.indexOf("Tweede")).toBe("1. Eerste.\n\n2. ".length);
  });
});

describe("eigenMarkeringenVoorContext", () => {
  const el = (p: Partial<AnnotatieElement>): AnnotatieElement =>
    ({
      id: "e1", klasse: "Rechtssubject", tekst: "de ontvanger", lid: "1", toelichting: "",
      vindplaats: "", herkomst: "agent", lifecycle: "proposed", alternatieven: [],
      critic_rondes: [], aandacht: null, critic: "", anker: null, ...p,
    }) as AnnotatieElement;

  const doc = (elementen: AnnotatieElement[]): AnnotatieDocument =>
    ({
      slug: "iw-art8", bwbId: "BWBR0004770", artikel: "8", lid: "1", werkgebied: "IW 1990",
      status: "in_review", elementen,
    }) as AnnotatieDocument;

  it("neemt alleen de markeringen van de jurist mee", () => {
    const uit = eigenMarkeringenVoorContext(
      doc([el({ id: "a", herkomst: "agent" }), el({ id: "m", herkomst: "mens" })]),
    );
    expect(uit.map((e) => e.id)).toEqual(["m"]);
  });

  it("laat verworpen markeringen weg", () => {
    const uit = eigenMarkeringenVoorContext(
      doc([
        el({ id: "m1", herkomst: "mens" }),
        el({ id: "m2", herkomst: "mens", lifecycle: "rejected" }),
      ]),
    );
    expect(uit.map((e) => e.id)).toEqual(["m1"]);
  });

  it("geeft niets terug zonder document", () => {
    // Een verse annotatie-opdracht heeft nog geen document; dan is er ook geen eigen werk om
    // langs de Critic te leggen. Eerder gingen hier de markeringen van álle geopende documenten in.
    expect(eigenMarkeringenVoorContext(undefined)).toEqual([]);
  });

  it("begrenst de lijst", () => {
    const veel = Array.from({ length: 40 }, (_, i) => el({ id: `m${i}`, herkomst: "mens" }));
    expect(eigenMarkeringenVoorContext(doc(veel))).toHaveLength(20);
  });
});

describe("annotatieTitel", () => {
  const basis = { bwbId: "BWBR0004770", artikel: "9", lid: "" };

  it("zet naam en vindplaats samen tot één label", () => {
    expect(annotatieTitel({ ...basis, citeertitel: "Invorderingswet 1990" })).toBe(
      "Invorderingswet 1990 — art. 9",
    );
  });

  it("neemt het lid mee als het document op één lid is afgebakend", () => {
    expect(annotatieTitel({ ...basis, citeertitel: "Invorderingswet 1990", lid: "2" })).toBe(
      "Invorderingswet 1990 — art. 9 lid 2",
    );
  });

  it("valt terug op werkgebied en dan op het bwbId, net als de server", () => {
    expect(annotatieTitel({ ...basis, werkgebied: "Uitstel van betaling" })).toBe(
      "Uitstel van betaling — art. 9",
    );
    expect(annotatieTitel(basis)).toBe("BWBR0004770 — art. 9");
  });
});

describe("isVerwijderd", () => {
  it("herkent de 404 als 'bestaat niet (meer)'", () => {
    // De api geeft 404 zowel bij een verwijderd document als bij dat van iemand anders; voor de UI
    // is dat hetzelfde: opnieuw proberen kan niet slagen.
    expect(isVerwijderd({ status: 404, detail: "Onbekend annotatie-document: doc-x" })).toBe(true);
  });

  it("laat storingen storingen blijven (die mogen wél een retry houden)", () => {
    expect(isVerwijderd({ status: 502, detail: "Upstream onbereikbaar" })).toBe(false);
    expect(isVerwijderd({ status: 504, detail: "Wachttijd verstreken" })).toBe(false);
  });

  it("is geen ApiError → geen verwijderd", () => {
    expect(isVerwijderd(new Error("netwerk weg"))).toBe(false);
    expect(isVerwijderd(undefined)).toBe(false);
  });
});

describe("vraagSuggesties", () => {
  it("noemt de klasse van het element in de eerste vraag", () => {
    const [eerste] = vraagSuggesties(el("a", { klasse: "Tijdsaanduiding" }));
    expect(eerste).toBe("Waarom is dit een Tijdsaanduiding?");
  });

  it("vraagt bij twijfel naar het alternatief", () => {
    // Daar zit het verschil per element: "waarom geen Voorwaarde?" is scherper dan welke vaste
    // formulering ook, en de agent heeft dat alternatief zelf voorgesteld.
    const met = vraagSuggesties(el("a", {
      klasse: "Tijdsaanduiding",
      alternatieven: [{ klasse: "Voorwaarde", motivatie: "kan ook een conditie zijn" }],
    }));
    expect(met[2]).toBe("Waarom geen Voorwaarde?");
  });

  it("valt zonder alternatieven terug op de samenhang", () => {
    const zonder = vraagSuggesties(el("a", { klasse: "Tijdsaanduiding", alternatieven: [] }));
    expect(zonder[2]).toBe("Hoe verhoudt dit zich tot de rest van het artikel?");
  });

  it("levert er altijd precies drie, en geen dubbele", () => {
    const vragen = vraagSuggesties(el("a", {
      klasse: "Voorwaarde",
      alternatieven: [{ klasse: "Tijdsaanduiding", motivatie: "" }],
    }));
    expect(vragen).toHaveLength(3);
    expect(new Set(vragen).size).toBe(3);
  });
});
