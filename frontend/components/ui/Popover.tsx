"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { klemHorizontaal } from "@/lib/popover";

interface PopoverProps {
  trigger: (open: boolean, toggle: () => void) => ReactNode;
  children: ReactNode;
  className?: string;
  /** Toegankelijke naam voor het paneel (role="dialog"). */
  ariaLabel?: string;
  /** Aangeroepen vlak vóór het paneel sluit (Escape, outside-click, of toggle) — zodat de
   * aanroeper zelf de focus kan terugzetten op de trigger. Popover kent de trigger zelf niet. */
  onClose?: () => void;
  /** Volledige positionering van het paneel (plaatsing én richting), relatief aan de wrapper.
   * Default `right-0 top-full mt-1`: onder de trigger, naar links uitklappend. De aanroeper bepaalt
   * dit zelf omdat alleen die weet hoeveel ruimte er is — in een smalle kolom is `inset-x-3 top-full`
   * (volle kolombreedte) juist, en boven aan een scherm `bottom-full mb-1` (omhoog uitklappend). */
  positie?: string;
  /** Klassen van de wrapper om trigger + paneel. Default `relative`, zodat het paneel aan de
   * trigger hangt. Zet dit op `static` als een parent het ankerpunt moet zijn — bijvoorbeeld om
   * het paneel de volle breedte van een kolom te laten volgen in plaats van die van de knop. */
  containerClassName?: string;
}

export function Popover({ trigger, children, className = "", ariaLabel, onClose, positie = "right-0 top-full mt-1", containerClassName = "relative" }: PopoverProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const paneelRef = useRef<HTMLDivElement>(null);
  // Verschuiving die het paneel binnen het scherm houdt. De `positie` hangt hem aan zijn trigger,
  // maar die weet niet waar hij op het scherm staat: een rechts uitgelijnd paneel bij een knop die
  // zelf rechts staat, steekt links buiten beeld. Op een telefoon las de exportlijst zo met de
  // eerste tekens eraf.
  const [dx, setDx] = useState(0);

  function close() {
    onClose?.();
    setOpen(false);
  }

  function toggle() {
    setOpen((v) => {
      if (v) onClose?.();
      return !v;
    });
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
    // Bewust alleen `open` als dependency: `close` leest onClose/setOpen via closure en hoeft
    // niet opnieuw gebonden te worden bij elke render van de aanroeper (onClose is vaak een
    // inline callback, dus een andere referentie per render — dat zou de listeners onnodig
    // laten flapperen zolang het paneel open staat).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Meten en corrigeren gebeurt vóór de browser schildert (`useLayoutEffect`), anders zie je het
  // paneel eerst verkeerd staan en dan verspringen. Alleen horizontaal: verticaal kiest de
  // aanroeper zelf een richting (`top-full` of `bottom-full`), en dat is de as waar hij wél zicht
  // op heeft.
  useLayoutEffect(() => {
    if (!open || !paneelRef.current) {
      setDx(0);
      return;
    }
    const rect = paneelRef.current.getBoundingClientRect();
    setDx(klemHorizontaal({ left: rect.left - dx, breedte: rect.width }, window.innerWidth));
    // `dx` bewust buiten de dependencies: hij wordt hier gezet, en de meting rekent hem er zelf uit
    // terug. Zou hij erin staan, dan meet dit effect zichzelf aan het schuiven.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <div ref={ref} className={containerClassName}>
      {trigger(open, toggle)}
      {open && (
        <div
          ref={paneelRef}
          role="dialog"
          aria-label={ariaLabel}
          className={`absolute z-40 ${positie} ${className}`}
          style={dx ? { transform: `translateX(${dx}px)` } : undefined}
        >
          {children}
        </div>
      )}
    </div>
  );
}
