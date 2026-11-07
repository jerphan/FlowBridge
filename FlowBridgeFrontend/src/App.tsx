import {useState} from "react";
import FileUploader from "./components/FileUploader";
import StartButton from "./components/StartButton";
import ProjectViewer from "./components/ProjectViewer";
import GitHubUploader from "./components/GitHubUploader"
import DiagramManager from "./components/DiagramManager"
import {flowchartJSON, pyProject, sourceFile} from "./types/types";
import axios from "axios";

const api = axios.create({
    baseURL: "http://localhost:8000"
})

function app(){
    const [project, setProject] = useState<pyProject | null>(null);
    const [selectedFile, setSelectedFile] = useState<sourceFile | null>(null);
    const [flowChart, setFlowchart] = useState<flowchartJSON | null>(null);

    const handleProjectLoaded = (project : pyProject) =>{
        setProject(project);
        setSelectedFile(project.files[0]);
        setFlowchart(null);
    }

    return <>
            <head>
                <meta charSet="UTF-8"/>
                <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
                <title>FlowBridge</title>
            </head>
            <header className="heading">
                <div className="headingLeft">
                    <img src="./FlowBridgeIcon.png" alt="Logo Icon" className="logoIcon"/>
                    <span className="brandName">FlowBridge</span>
                </div>
                    <StartButton project={project} selectedFile={selectedFile} onFlowChartLoaded={(loadedFlowchart) => setFlowchart(loadedFlowchart)}/>
                <div className="headingRight">
                    <div className="user-profile">
                        <div>
                            <label htmlFor="loginButton">
                                <img src="./ProfilePicture.png" alt="Profile Icon" className="loginIcon"/>
                            </label>
                            <input type="button" id="loginButton" className="toolButton"/>
                        </div>
                    </div>
                </div>
        </header>
        <div className="workspace">
                <aside className="sidebarLeft">
                    <div className="toolbarTop">
                        <div>
                            <FileUploader onProjectLoaded={handleProjectLoaded}/>
                        </div>
                        <div>
                            <GitHubUploader onProjectLoaded={handleProjectLoaded}/>
                        </div>
                        <img src="ExportButton.png" alt="Export Icon" className="toolIcon"/>
                    </div>
                    <div className="toolbar-bottom">
                        <img src="SettingsIcon.png" alt="Settings Icon" className="toolIcon"/>
                    </div>
                </aside>
                <main className="contentGrid">
                    <section className="card">
                        <div className="cardHeader">
                            Source Code
                        </div>
                            <ProjectViewer project = {project} onSelectFile={(file) => setSelectedFile(file)}/>
                        <div className="cardBody"></div>
                    </section>

                    <section className="card">
                        <div className="cardHeader">FlowChart</div>
                        <div className="cardBody">
                            <DiagramManager flowchart = {flowChart} selectedFile={selectedFile}/>
                        </div>
                    </section>
                </main>
            </div>
    </>;
}

export default app;