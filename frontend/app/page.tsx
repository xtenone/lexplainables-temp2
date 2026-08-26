import { redirect } from "next/navigation";

// De app is de werkplek (chat-werkruimte tegen graph-qa). De home leidt daarheen door;
// de analyse-webapp (projectenlijst/aanmaken/review/rapport) is verwijderd.
export default function Home() {
  redirect("/workbench");
}
