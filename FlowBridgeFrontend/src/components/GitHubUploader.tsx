import {ChangeEvent, FormEvent, useState, useEffect, useRef} from 'react';
import "../App.css";
import axios, {AxiosError} from 'axios';
import {errorResponse, pyProject, uploadStatus} from "../types/types"

const api = axios.create({
    baseURL: "http://localhost:8000"
})

export interface linkUploaderProperties{
    onProjectLoaded: (project: pyProject) => void;
    projectName?: string;
}

export default function LinkUploader({onProjectLoaded, projectName=""}: linkUploaderProperties){
    //The modal by default is closed
    const dialogRef = useRef<HTMLDialogElement | null>(null);
    const [URL, setURL] = useState<string>("");
    //Setting the constants for the full project and then the selectedFile to display later
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [pyProjectName, setPyProjectName] = useState<string>(projectName)
    //Setting default state for the status of a file upload
    const [status, setStatus] = useState<uploadStatus>("idle");
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

    const handleUploadError = (error : unknown) => {
        //If the axios detects that a caught error was cancelled, then we just set the state back to idle
        if(axios.isCancel(error)){
            setStatus("idle")
            return;
        }
        //Otherwise we set the status of the upload to error
        setStatus("error")
        const axiosErr = error as AxiosError<errorResponse>
    };

    const uploadGitHub = async (linkUpload : string) =>{
        controllerRef.current?.abort();
        const controller = new AbortController();
        controllerRef.current = controller;

        //Set the useStates to the appropriate states before beginning the upload logic
        setStatus("uploading")
        setError(null);
        setErrorCode(null);

        try{
            const response = await api.post<pyProject>("/api/projects/github", linkUpload,{
                signal : controller.signal,
            });
            //If the controller did not abort, then the response was a success
            setStatus("success")
            onProjectLoaded(response.data);
        }
        catch(err){
            handleUploadError(err);
        }
    };
    
    const handleLinkChange = async (e:ChangeEvent<HTMLInputElement>) =>{
        setURL(e.target.value);
    };

    //Handling when the user submits through the modal
    const handleSubmit = async (e: ChangeEvent<HTMLFormElement>) => {
        e.preventDefault();
        if(!URL.trim()){
            return;
        }
        await uploadGitHub(URL.trim());
    };

    function openDialog(){
        if(!dialogRef.current){
            return;
        }
        dialogRef.current.hasAttribute("open")
            ?dialogRef.current.close()
            :dialogRef.current.showModal();
    };

    return (
        <>
            <label htmlFor = "URLupload">
                <img src="linkIcon.png" alt="Upload Icon" className="toolIcon"/>
            </label>
            <button id = "URLupload" type="button" onClick={openDialog} className="toolButton"></button>
            <dialog ref={dialogRef}>
                <form method = "dialog" onSubmit={handleSubmit}>
                    <div>
                        <label htmlFor="urlInput"><b>URL</b></label>
                        <input id="urlInput" type="text" placeholder="Enter URL" name="URL" required/>
                        <button type="submit">Login</button>
                    </div>
                </form>
            </dialog>
        </>
    );
}