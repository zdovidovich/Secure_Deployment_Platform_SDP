from flask import Blueprint, redirect, render_template

from services.deployment_store import deployment_store

web_bp = Blueprint("deploy", __name__, url_prefix="/deploy")


@web_bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@web_bp.route("/status/<deployment_id>", methods=["GET"])
def status(deployment_id: str):
    job = deployment_store.get(deployment_id)
    if not job:
        return render_template("deploy_not_found.html", session_id=deployment_id), 404

    return render_template(
        "deploy_status.html",
        session_id=deployment_id,
        status=job.service.status,
    )


@web_bp.route("/api/status/<deployment_id>", methods=["GET"])
def legacy_status(deployment_id: str):
    return redirect(f"/api/v1/deployments/{deployment_id}", code=307)
