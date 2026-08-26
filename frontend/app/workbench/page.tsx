import { WerkplekClient } from "@/components/werkplek/WerkplekClient";

export const metadata = { title: "Assistent · Wetsanalyse" };

export default function WerkplekPagina() {
  return (
    <div className="animate-rise">
      <WerkplekClient />
    </div>
  );
}
