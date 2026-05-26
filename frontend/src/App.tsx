import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import DataPipeline from "./pages/DataPipeline";
import AgentTasks from "./pages/AgentTasks";
import HPCResources from "./pages/HPCResources";
import RLHFTraining from "./pages/RLHFTraining";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/data" replace />} />
        <Route path="/data" element={<DataPipeline />} />
        <Route path="/agents" element={<AgentTasks />} />
        <Route path="/hpc" element={<HPCResources />} />
        <Route path="/rlhf" element={<RLHFTraining />} />
      </Route>
    </Routes>
  );
}
