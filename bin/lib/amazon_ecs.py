# import json
from typing import Dict
from lib.env import Config
from lib.amazon import ecs_client, ec2_client


def get_detail_value(details, name):
    for detail in details:
        if detail["name"] == name:
            return detail["value"]
    raise RuntimeError(f"Value not found for {name} in details")


def get_instance_details_for_task(task):
    taskdetails = task["attachments"][0]["details"]

    return {
        "private_ip_address": get_detail_value(taskdetails, "privateIPv4Address"),
        "state": task["lastStatus"],
        "public_ip_address": task["PublicIp"],
        "health": task["healthStatus"],
    }


class ECSEnvironments:
    def __init__(self):
        self.default_cluster = self._get_default_cluster()
        self.service_arns = self._get_service_arns()
        self.services = self._get_service_descriptions(self.service_arns)
        self.reload_tasks()

    def reload_tasks(self):
        self.task_arns = self._get_task_arns()
        self.tasks = self._get_task_descriptions(self.task_arns)
        self.task_definitions: Dict[str, any] = {}

        self.task_definition_arns = self._get_taskdef_arns()
        for taskdef_arn in self.task_definition_arns:
            if not taskdef_arn in self.task_definitions:
                self.task_definitions[taskdef_arn] = self._get_task_definition(taskdef_arn)

    def _get_default_cluster(self):
        res = ecs_client.list_clusters()
        return res["clusterArns"][0]

    def _get_service_descriptions(self, service_arns):
        res = ecs_client.describe_services(cluster=self.default_cluster, services=service_arns)
        return res["services"]

    def _get_service_arns(self):
        res = ecs_client.list_services(cluster=self.default_cluster)
        return res["serviceArns"]

    def _get_taskdef_arns(self):
        res = ecs_client.list_task_definitions()
        return res["taskDefinitionArns"]

    def _get_task_arns(self):
        res = ecs_client.list_tasks(cluster=self.default_cluster)
        return res["taskArns"]

    def _get_task_descriptions(self, task_arns):
        if len(task_arns) > 0:
            res = ecs_client.describe_tasks(cluster=self.default_cluster, tasks=task_arns)
            return res["tasks"]
        else:
            return []

    def _get_task_definition(self, taskdef_arn):
        res = ecs_client.describe_task_definition(taskDefinition=taskdef_arn)
        return res["taskDefinition"]

    def _get_ce_env(self, taskdef):
        if len(taskdef["containerDefinitions"]) > 0:
            for envvar in taskdef["containerDefinitions"][0]["environment"]:
                if envvar["name"] == "CE_ENV":
                    return envvar["value"]
        return ""

    def _get_taskdef_for_config(self, cfg: Config):
        for taskdef_arn in self.task_definitions:
            if self._get_ce_env(self.task_definitions[taskdef_arn]) == cfg.env.value:
                return self.task_definitions[taskdef_arn]
        return

    def _get_service_with_taskdef(self, taskdef):
        for service in self.services:
            if service["taskDefinition"] == taskdef["taskDefinitionArn"]:
                return service

    def get_counts_for_config(self, cfg: Config):
        taskdef = self._get_taskdef_for_config(cfg)
        if taskdef:
            service = self._get_service_with_taskdef(taskdef)

            return [service["desiredCount"], service["runningCount"]]
        else:
            raise RuntimeError("Cant find task definition for config")

    def get_service_for_config(self, cfg: Config):
        taskdef = self._get_taskdef_for_config(cfg)
        if taskdef:
            return self._get_service_with_taskdef(taskdef)
        else:
            return

    def get_containers_for_config(self, cfg: Config):
        containers = []

        taskdef = self._get_taskdef_for_config(cfg)
        for task in self.tasks:
            if task["taskDefinitionArn"] == taskdef["taskDefinitionArn"]:
                containers += [task["containers"]]

        return containers

    def get_public_ip_for_netintf(self, network_interface_id):
        descriptions = ec2_client.describe_network_interfaces(NetworkInterfaceIds=[network_interface_id])
        return descriptions["NetworkInterfaces"][0]["Association"]["PublicIp"]

    def get_network_interface_id_of_task(self, task):
        return get_detail_value(task["attachments"][0]["details"], "networkInterfaceId")

    def get_tasks_for_config(self, cfg: Config):
        tasks = []

        taskdef = self._get_taskdef_for_config(cfg)
        for task in self.tasks:
            if task["taskDefinitionArn"] == taskdef["taskDefinitionArn"]:
                netid = self.get_network_interface_id_of_task(task)
                if netid:
                    task["PublicIp"] = self.get_public_ip_for_netintf(netid)
                tasks += [task]

        return tasks

    def update_desired_count(self, cfg: Config, count):
        service = self.get_service_for_config(cfg)
        ecs_client.update_service(cluster=self.default_cluster, service=service["serviceArn"], desiredCount=count)

    # print(json.dumps(task0desc, indent=4, sort_keys=True, default=str))
