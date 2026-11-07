import {useState, useEffect, useRef} from 'react';
import "../App.css"
import axios, {AxiosError} from 'axios';
import {errorResponse, flowchartJSON, pyProject, sourceFile, uploadStatus} from "../types/types";

const api = axios.create({
    baseURL: "http://localhost:8000"
})

export interface startButtonProperties{
    //Keeps track of the currently uploaded pyProject object
    project? : pyProject | null;
    selectedFile? : sourceFile | null;
    onFlowChartLoaded? : (flowchart : flowchartJSON) => void
    revisionId? : number;
}

export default function StartButton({project = null, selectedFile = null, onFlowChartLoaded, revisionId = 1} : startButtonProperties){
    const [status, setStatus] = useState<uploadStatus>("idle")
    //Constants for errors, or error codes. They both can either be strings or null if there is no error
    const [error, setError] = useState<string | null>(null);
    const[errorCode, setErrorCode] = useState<string | null>(null);
    //The controller will cancel the request if needed. If not needed then it will be Null type
    const controllerRef = useRef<AbortController | null>(null);

    useEffect(()=> {
        return () => {
            controllerRef.current?.abort();
        }
    }, []);

    const handleAnalysisError = (err : unknown) => {
        if(axios.isCancel(err)){
            setStatus("idle");
            return;
        }
        setStatus("error");
    }

    const handleStartClick = async () => {
        //If the user attempts to start flow chart generation with nothign loaded then we set the status to error
        if(!project){
            setStatus("error");
            setError("No project uploaded to generate flowchart")
            return;
        }

        controllerRef.current?.abort();
        const controller = new AbortController();
        controllerRef.current = controller;

        setStatus("uploading");
        setError(null);
        setErrorCode(null);

        try{
            const response = await api.get<flowchartJSON | {flowchart : flowchartJSON}>(
                `/api/projects/${project.projectID}/flowchart`,{
                    params : {revisionId},
                    signal : controller.signal,
                });
            const flowchartJSON = "flowchart" in response.data? response.data.flowchart : response.data;
            setStatus("success");
            onFlowChartLoaded?.(flowchartJSON)
        }
        catch(err){
            handleAnalysisError(err);
        }
    };

    return(
        <>
            <div className="headingCenter">
                <button type = "button" className="startButton" onClick={handleStartClick}>
                    <img src="./StartButton.png" alt="Start Button"/>
                </button>
            </div>
        </>
    );
}
