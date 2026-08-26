import { redirect } from "next/navigation";

/** Account is opgegaan in het instellingenvenster. Deze route blijft als doorverwijzing bestaan voor
 *  bestaande links en bladwijzers. */
export default function AccountPagina() {
  redirect("/instellingen/account");
}
