import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import MolecularDatabase from "./pages/MolecularDatabase";
import LiteratureResearch from "./pages/LiteratureResearch";
import PropertyPrediction from "./pages/PropertyPrediction";
import ChemistryToolbox from "./pages/ChemistryToolbox";
import AgentConsole from "./pages/AgentConsole";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/database" replace />} />
        <Route path="/database" element={<MolecularDatabase />} />
        <Route path="/literature" element={<LiteratureResearch />} />
        <Route path="/prediction" element={<PropertyPrediction />} />
        <Route path="/experiments" element={<ChemistryToolbox />} />
        <Route path="/agent" element={<AgentConsole />} />
      </Route>
    </Routes>
  );
}
