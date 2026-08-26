import { redirect } from "next/navigation";

/** Beheer is opgegaan in het instellingenvenster (tabs onder /instellingen/beheer/…). Deze route
 *  blijft als doorverwijzing bestaan; de rolgate zit op het doelpad. */
export default function BeheerPagina() {
  redirect("/instellingen/beheer/modelprofielen");
}
