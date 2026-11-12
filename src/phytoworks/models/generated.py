"""Generated wire models from the committed Hub OpenAPI artifact.

DO NOT EDIT BY HAND. This file is generated from the Hub OpenAPI document by
``scripts/generate_models.py`` in the PhytoWorks repository.

Every class derives from ``phytoworks.models._base.WireModel``; the
allowlist in ``scripts/model-allowlist.json`` decides which components
exist here.  Inline objects were hoisted under these names:
  AccessInfoCurrentOrganization <- AccessInfo.currentOrganization
  AccessInfoUser <- AccessInfo.user
  ActionExecutionBatchStatusExecutionsValue <- ActionExecutionBatchStatus.executions{}
  ActionExecutionSearchResultItem <- ActionExecutionSearchResult.items[]
  ActionExecutionSearchResultPagination <- ActionExecutionSearchResult.pagination
  ActionExecutionStatusError <- ActionExecutionStatus.<anyOf:Error>
  ActionExecutionStatusResultCache <- ActionExecutionStatus.<anyOf:Result>.<oneOf:Cache>
  ActionExecutionStatusResultDb <- ActionExecutionStatus.<anyOf:Result>.<oneOf:Db>
  BandProvenanceBandInterpretation <- BandProvenance.bandInterpretation
  BandProvenanceBandInterpretationBandApprovedProfile <- BandProvenance.bandInterpretation.bands[].<oneOf:ApprovedProfile>
  BandProvenanceBandInterpretationBandApprovedProfileBasis <- BandProvenance.bandInterpretation.bands[].<oneOf:ApprovedProfile>.basis
  BandProvenanceBandInterpretationBandUnresolved <- BandProvenance.bandInterpretation.bands[].<oneOf:Unresolved>
  BandProvenanceBandInterpretationBandUserConfirmed <- BandProvenance.bandInterpretation.bands[].<oneOf:UserConfirmed>
  BandProvenanceBandInterpretationBandVerifiedMetadata <- BandProvenance.bandInterpretation.bands[].<oneOf:VerifiedMetadata>
  BandProvenanceBandInterpretationBandVerifiedMetadataBasis <- BandProvenance.bandInterpretation.bands[].<oneOf:VerifiedMetadata>.basis
  BandProvenanceBandRegistrationRegisteredCameraMetadata <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:CameraMetadata>
  BandProvenanceBandRegistrationRegisteredCameraMetadataAligner <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:CameraMetadata>.aligner
  BandProvenanceBandRegistrationRegisteredCameraMetadataGrid <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:CameraMetadata>.grid
  BandProvenanceBandRegistrationRegisteredCameraMetadataRecordedBy <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:CameraMetadata>.recordedBy
  BandProvenanceBandRegistrationRegisteredCameraMetadataTransform <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:CameraMetadata>.transforms[]
  BandProvenanceBandRegistrationRegisteredManualProfile <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>
  BandProvenanceBandRegistrationRegisteredManualProfileAligner <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.aligner
  BandProvenanceBandRegistrationRegisteredManualProfileGrid <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.grid
  BandProvenanceBandRegistrationRegisteredManualProfileProfile <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.profile
  BandProvenanceBandRegistrationRegisteredManualProfileRecordedBy <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.recordedBy
  BandProvenanceBandRegistrationRegisteredManualProfileTransform <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.transforms[]
  BandProvenanceBandRegistrationRegisteredProcessedProduct <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ProcessedProduct>
  BandProvenanceBandRegistrationRegisteredProcessedProductGrid <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ProcessedProduct>.grid
  BandProvenanceBandRegistrationRegisteredProcessedProductRecordedBy <- BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ProcessedProduct>.recordedBy
  BandProvenanceBandRegistrationUnknown <- BandProvenance.bandRegistration.<anyOf:Unknown>
  BandProvenanceBandRegistrationUnknownRecordedBy <- BandProvenance.bandRegistration.<anyOf:Unknown>.recordedBy
  BandProvenanceBandRegistrationUnregistered <- BandProvenance.bandRegistration.<anyOf:Unregistered>
  BandProvenanceBandRegistrationUnregisteredRecordedBy <- BandProvenance.bandRegistration.<anyOf:Unregistered>.recordedBy
  BandProvenanceNormalization <- BandProvenance.normalization
  BandProvenanceNormalizationRecord <- BandProvenance.normalization.record
  BandProvenanceNormalizationRecordConverter <- BandProvenance.normalization.record.converter
  BandProvenanceNormalizationRecordSourceDeviceProfile <- BandProvenance.normalization.record.sources[].<oneOf:DeviceProfile>
  BandProvenanceNormalizationRecordSourceFile <- BandProvenance.normalization.record.sources[].<oneOf:File>
  BandProvenanceNormalizationRecordSourceFileBand <- BandProvenance.normalization.record.sources[].<oneOf:File>.bands[]
  BandProvenanceNormalizationRef <- BandProvenance.normalization.ref
  BandProvenanceZarrSeal <- BandProvenance.zarrSeal
  BandProvenanceZarrSealMember <- BandProvenance.zarrSeal.members[]
  CaptureSessionDetailDevice <- CaptureSessionDetail.device
  CaptureSessionDetailMedia <- CaptureSessionDetail.media[]
  CaptureSessionDetailMediaOriginal <- CaptureSessionDetail.media[].original
  CaptureSessionDetailMediaProvenance <- CaptureSessionDetail.media[].provenance
  CaptureSessionDetailMediaProvenanceActor <- CaptureSessionDetail.media[].provenance.actor
  CaptureSessionDetailSpot <- CaptureSessionDetail.spot
  CaptureSessionMedia <- CaptureSession.media[]
  CaptureSessionMediaOriginal <- CaptureSession.media[].original
  CaptureSessionMediaProvenance <- CaptureSession.media[].provenance
  CaptureSessionMediaProvenanceActor <- CaptureSession.media[].provenance.actor
  CaptureSessionSpot <- CaptureSession.spot
  CaptureSessionTag <- CaptureSession.tags[]
  ManualActionDryRunChecks <- ManualActionDryRun.checks
  ManualActionDryRunChecksConflict <- ManualActionDryRun.checks.conflict
  ManualActionDryRunChecksDefinition <- ManualActionDryRun.checks.definition
  ManualActionDryRunChecksOnline <- ManualActionDryRun.checks.online
  ManualActionDryRunChecksSchema <- ManualActionDryRun.checks.schema
  ManualActionDryRunChecksScope <- ManualActionDryRun.checks.scope
  MediaAssetOriginal <- MediaAsset.original
  MediaAssetProvenance <- MediaAsset.provenance
  MediaAssetProvenanceActor <- MediaAsset.provenance.actor
  PhenosSessionCreationCredential <- PhenosSessionCreation.credential
  PhenosSessionCreationSession <- PhenosSessionCreation.session
  PhenosSessionCreationSessionReferences <- PhenosSessionCreation.session.references
  PhenosSessionCreationSessionReferencesAnnotation <- PhenosSessionCreation.session.references.annotations[]
  PhenosSessionCreationSessionReferencesImage <- PhenosSessionCreation.session.references.image
  PhenosSessionCreationSessionReferencesImageSourceBinding <- PhenosSessionCreation.session.references.image.sourceBinding
  PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystem <- PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem
  PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAngleConvention <- PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.angleConvention
  PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxes <- PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.axes
  PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxesX <- PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.axes.x
  PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxesY <- PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.axes.y
  PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemDimensions <- PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.dimensions
  PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemPixelOrigin <- PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.pixelOrigin
  PhenosSessionCreationSessionReferencesImageSourceBindingGridExifApplied <- PhenosSessionCreation.session.references.image.sourceBinding.grid.<oneOf:ExifApplied>
  PhenosSessionCreationSessionReferencesImageSourceBindingGridExifAppliedStoredDimensions <- PhenosSessionCreation.session.references.image.sourceBinding.grid.<oneOf:ExifApplied>.storedDimensions
  PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlane <- PhenosSessionCreation.session.references.image.sourceBinding.grid.<oneOf:NativePlane>
  PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlaneAxe <- PhenosSessionCreation.session.references.image.sourceBinding.grid.<oneOf:NativePlane>.axes[]
  PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlaneDimensions <- PhenosSessionCreation.session.references.image.sourceBinding.grid.<oneOf:NativePlane>.dimensions
  PhenosSessionCreationSessionReferencesImageSourceBindingPlane <- PhenosSessionCreation.session.references.image.sourceBinding.plane
  PhenosSessionCreationSessionReferencesImageSourceBindingPlaneAxisSelection <- PhenosSessionCreation.session.references.image.sourceBinding.plane.axisSelection
  PhenosSessionReferences <- PhenosSession.references
  PhenosSessionReferencesAnnotation <- PhenosSession.references.annotations[]
  PhenosSessionReferencesImage <- PhenosSession.references.image
  PhenosSessionReferencesImageSourceBinding <- PhenosSession.references.image.sourceBinding
  PhenosSessionReferencesImageSourceBindingCoordinateSystem <- PhenosSession.references.image.sourceBinding.coordinateSystem
  PhenosSessionReferencesImageSourceBindingCoordinateSystemAngleConvention <- PhenosSession.references.image.sourceBinding.coordinateSystem.angleConvention
  PhenosSessionReferencesImageSourceBindingCoordinateSystemAxes <- PhenosSession.references.image.sourceBinding.coordinateSystem.axes
  PhenosSessionReferencesImageSourceBindingCoordinateSystemAxesX <- PhenosSession.references.image.sourceBinding.coordinateSystem.axes.x
  PhenosSessionReferencesImageSourceBindingCoordinateSystemAxesY <- PhenosSession.references.image.sourceBinding.coordinateSystem.axes.y
  PhenosSessionReferencesImageSourceBindingCoordinateSystemDimensions <- PhenosSession.references.image.sourceBinding.coordinateSystem.dimensions
  PhenosSessionReferencesImageSourceBindingCoordinateSystemPixelOrigin <- PhenosSession.references.image.sourceBinding.coordinateSystem.pixelOrigin
  PhenosSessionReferencesImageSourceBindingGridExifApplied <- PhenosSession.references.image.sourceBinding.grid.<oneOf:ExifApplied>
  PhenosSessionReferencesImageSourceBindingGridExifAppliedStoredDimensions <- PhenosSession.references.image.sourceBinding.grid.<oneOf:ExifApplied>.storedDimensions
  PhenosSessionReferencesImageSourceBindingGridNativePlane <- PhenosSession.references.image.sourceBinding.grid.<oneOf:NativePlane>
  PhenosSessionReferencesImageSourceBindingGridNativePlaneAxe <- PhenosSession.references.image.sourceBinding.grid.<oneOf:NativePlane>.axes[]
  PhenosSessionReferencesImageSourceBindingGridNativePlaneDimensions <- PhenosSession.references.image.sourceBinding.grid.<oneOf:NativePlane>.dimensions
  PhenosSessionReferencesImageSourceBindingPlane <- PhenosSession.references.image.sourceBinding.plane
  PhenosSessionReferencesImageSourceBindingPlaneAxisSelection <- PhenosSession.references.image.sourceBinding.plane.axisSelection
  RecipeBatchPageCounts <- RecipeBatchPage.counts
  RecipeBatchPageRow <- RecipeBatchPage.rows[]
  RecipeBatchPageRowMetricsValue <- RecipeBatchPage.rows[].metrics{}
  RecipeBatchPageRowScale <- RecipeBatchPage.rows[].scale
  RecipeBatchPageRowTag <- RecipeBatchPage.rows[].tags[]
  RecipeDetailDefinition <- RecipeDetail.definition
  RecipeDetailDefinitionSlotAnnotations <- RecipeDetail.definition.slots[].<oneOf:Annotations>
  RecipeDetailDefinitionSlotAnnotationsSelectAll <- RecipeDetail.definition.slots[].<oneOf:Annotations>.select.<anyOf:All>
  RecipeDetailDefinitionSlotAnnotationsSelectTag <- RecipeDetail.definition.slots[].<oneOf:Annotations>.select.<anyOf:Tag>
  RecipeDetailDefinitionSlotPhoto <- RecipeDetail.definition.slots[].<oneOf:Photo>
  RecipeDetailDefinitionStep <- RecipeDetail.definition.steps[]
  RecipeDetailDefinitionStepInputsValue <- RecipeDetail.definition.steps[].inputs{}
  RecipeDetailVersion <- RecipeDetail.versions[]
  RecipeDetailVersionBasisCountOnly <- RecipeDetail.versions[].basis.<oneOf:CountOnly>
  RecipeDetailVersionBasisReadable <- RecipeDetail.versions[].basis.<oneOf:Readable>
  RecipeDetailVersionBasisReadableEntry <- RecipeDetail.versions[].basis.<oneOf:Readable>.entries[]
  RecipeDetailVersionContextHidden <- RecipeDetail.versions[].context.<oneOf:Hidden>
  RecipeDetailVersionContextNone <- RecipeDetail.versions[].context.<oneOf:None>
  RecipeDetailVersionContextPhoto <- RecipeDetail.versions[].context.<oneOf:Photo>
  RecipeDetailVersionDefinition <- RecipeDetail.versions[].definition
  RecipeDetailVersionDefinitionSlotAnnotations <- RecipeDetail.versions[].definition.slots[].<oneOf:Annotations>
  RecipeDetailVersionDefinitionSlotAnnotationsSelectAll <- RecipeDetail.versions[].definition.slots[].<oneOf:Annotations>.select.<anyOf:All>
  RecipeDetailVersionDefinitionSlotAnnotationsSelectTag <- RecipeDetail.versions[].definition.slots[].<oneOf:Annotations>.select.<anyOf:Tag>
  RecipeDetailVersionDefinitionSlotPhoto <- RecipeDetail.versions[].definition.slots[].<oneOf:Photo>
  RecipeDetailVersionDefinitionStep <- RecipeDetail.versions[].definition.steps[]
  RecipeDetailVersionDefinitionStepInputsValue <- RecipeDetail.versions[].definition.steps[].inputs{}
  RecipeListRecipe <- RecipeList.recipes[]
  RecipeListRecipeDefinition <- RecipeList.recipes[].definition
  RecipeListRecipeDefinitionSlotAnnotations <- RecipeList.recipes[].definition.slots[].<oneOf:Annotations>
  RecipeListRecipeDefinitionSlotAnnotationsSelectAll <- RecipeList.recipes[].definition.slots[].<oneOf:Annotations>.select.<anyOf:All>
  RecipeListRecipeDefinitionSlotAnnotationsSelectTag <- RecipeList.recipes[].definition.slots[].<oneOf:Annotations>.select.<anyOf:Tag>
  RecipeListRecipeDefinitionSlotPhoto <- RecipeList.recipes[].definition.slots[].<oneOf:Photo>
  RecipeListRecipeDefinitionStep <- RecipeList.recipes[].definition.steps[]
  RecipeListRecipeDefinitionStepInputsValue <- RecipeList.recipes[].definition.steps[].inputs{}
  RecipeRunAgainRun <- RecipeRunAgain.runs[]
  RecipeRunStartRun <- RecipeRunStart.runs[]
  RecipeRunStep <- RecipeRun.steps[]
  RecipeRunStepOutput <- RecipeRun.steps[].outputs[]
  RecipeRunStepOutputMetricsValue <- RecipeRun.steps[].outputs[].metrics{}
  RecipeRunStepOutputProvenance <- RecipeRun.steps[].outputs[].provenance
  RecipeRunStepOutputProvenanceCodec <- RecipeRun.steps[].outputs[].provenance.codec
  RecipeSummaryDefinition <- RecipeSummary.definition
  RecipeSummaryDefinitionSlotAnnotations <- RecipeSummary.definition.slots[].<oneOf:Annotations>
  RecipeSummaryDefinitionSlotAnnotationsSelectAll <- RecipeSummary.definition.slots[].<oneOf:Annotations>.select.<anyOf:All>
  RecipeSummaryDefinitionSlotAnnotationsSelectTag <- RecipeSummary.definition.slots[].<oneOf:Annotations>.select.<anyOf:Tag>
  RecipeSummaryDefinitionSlotPhoto <- RecipeSummary.definition.slots[].<oneOf:Photo>
  RecipeSummaryDefinitionStep <- RecipeSummary.definition.steps[]
  RecipeSummaryDefinitionStepInputsValue <- RecipeSummary.definition.steps[].inputs{}
  RuleAction <- Rule.actions[]
  RuleActionActionDefinition <- Rule.actions[].actionDefinition
  RuleActionActionDefinitionNameTranslation <- Rule.actions[].actionDefinition.nameTranslation
  RuleActionCaptureSessionOptions <- Rule.actions[].captureSessionOptions
  RuleExecutionActionsExecuted <- RuleExecution.actionsExecuted[]
  RuleExecutionRule <- RuleExecution.rule
  RuleTriggerConfigCondition <- Rule.triggerConfig.<anyOf:Condition>
  RuleTriggerConfigCron <- Rule.triggerConfig.<anyOf:Cron>
  RuleTriggerConfigEvent <- Rule.triggerConfig.<anyOf:Event>
  SpotAgent <- Spot.agents[]
  SpotAgentDevice <- Spot.agents[].device
  SpotAgentRealtimeStatus <- Spot.agents[].realtimeStatus
  SpotAgentRealtimeStatusHealth <- Spot.agents[].realtimeStatus.health
  SpotAgentsSummary <- Spot.agentsSummary
  SpotAgentsSummaryAvgHealth <- Spot.agentsSummary.avgHealth
  SpotDeviceStats <- Spot.deviceStats
  SpotGroupParent <- SpotGroup.parent
  SpotStructureDevice <- SpotStructure.devices[]
  SpotStructureDeviceAction <- SpotStructure.devices[].actions[]
  SpotStructureDeviceActionMetadata <- SpotStructure.devices[].actions[].metadata
  SpotStructureDeviceActionMetadataUi <- SpotStructure.devices[].actions[].metadata.ui
  SpotStructureDeviceActionNameTranslation <- SpotStructure.devices[].actions[].nameTranslation
  SpotStructureDeviceComponent <- SpotStructure.devices[].components[]
  SpotStructureDeviceComponentAction <- SpotStructure.devices[].components[].actions[]
  SpotStructureDeviceComponentActionMetadata <- SpotStructure.devices[].components[].actions[].metadata
  SpotStructureDeviceComponentActionMetadataUi <- SpotStructure.devices[].components[].actions[].metadata.ui
  SpotStructureDeviceComponentActionNameTranslation <- SpotStructure.devices[].components[].actions[].nameTranslation
  SpotStructureDeviceComponentTopic <- SpotStructure.devices[].components[].topics[]
  SpotStructureDeviceComponentTopicMetadata <- SpotStructure.devices[].components[].topics[].metadata
  SpotStructureDeviceComponentTopicMetadataStateMappingValue <- SpotStructure.devices[].components[].topics[].metadata.stateMapping{}
  SpotStructureDeviceTopic <- SpotStructure.devices[].topics[]
  SpotStructureDeviceTopicMetadata <- SpotStructure.devices[].topics[].metadata
  SpotStructureDeviceTopicMetadataStateMappingValue <- SpotStructure.devices[].topics[].metadata.stateMapping{}
  SpotStructureRule <- SpotStructure.rules[]
  SpotStructureRuleAction <- SpotStructure.rules[].actions[]
  SpotStructureRuleActionActionDefinition <- SpotStructure.rules[].actions[].actionDefinition
  SpotStructureRuleActionActionDefinitionNameTranslation <- SpotStructure.rules[].actions[].actionDefinition.nameTranslation
  SpotStructureRuleActionCaptureSessionOptions <- SpotStructure.rules[].actions[].captureSessionOptions
  SpotStructureRuleTriggerConfigCondition <- SpotStructure.rules[].triggerConfig.<anyOf:Condition>
  SpotStructureRuleTriggerConfigCron <- SpotStructure.rules[].triggerConfig.<anyOf:Cron>
  SpotStructureRuleTriggerConfigEvent <- SpotStructure.rules[].triggerConfig.<anyOf:Event>
  SpotStructureSpot <- SpotStructure.spot
  SpotStructureStats <- SpotStructure.stats
  SpotTag <- Spot.tags[]

Generator: datamodel-code-generator 0.76.1
Artifact SHA-256: 512ceacca08c3ca3158df48829def6217c2e7d074dd6ab877e0bc5aa46779f85
Allowlist: scripts/model-allowlist.json
Allowlist SHA-256: a66174e43bc3c1e641cfbff48997c4fbb0c156b12d2424bc666d9b8537e10dd4
Body SHA-256: c780ff31c56668808f557658e8de827e70c0cd0a6d779fbbf88f1e6b0b3c9142
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, ConfigDict, Field, RootModel

from phytoworks.models._base import WireModel


class AccessInfo(WireModel):
    """
    Wire model for OpenAPI component AccessInfoResponseDto.
    """

    user: AccessInfoUser
    roles: list[str]
    permissions: list[str]
    effective_permissions: Annotated[list[str], Field(alias="effectivePermissions")]
    organization_permissions: Annotated[list[str] | None, Field(alias="organizationPermissions")] = None
    system_role: Annotated[str, Field(alias="systemRole")]
    organization_role: Annotated[str | None, Field(alias="organizationRole")] = None
    current_organization: Annotated[AccessInfoCurrentOrganization | None, Field(alias="currentOrganization")] = None


class AccessInfoCurrentOrganization(WireModel):
    """
    Inline object hoisted from AccessInfo.currentOrganization.
    """

    id: str
    name: str
    slug: str | None = None
    role: str | None = None


class AccessInfoUser(WireModel):
    """
    Inline object hoisted from AccessInfo.user.
    """

    id: str
    email: str
    name: str | None = None


class AccessKey(WireModel):
    """
    Untyped in the committed OpenAPI artifact: ManagementAccessKeysController_listAccessKeys declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class ActionExecutionBatchStatus(WireModel):
    """
    Wire model for OpenAPI component ActionExecutionBatchStatusResponseDto.
    """

    executions: dict[str, ActionExecutionBatchStatusExecutionsValue]


class ActionExecutionBatchStatusExecutionsValue(WireModel):
    """
    Inline object hoisted from ActionExecutionBatchStatus.executions{}.
    """

    execution_id: Annotated[str, Field(alias="executionId")]
    action_def_id: Annotated[str, Field(alias="actionDefId")]
    status: str
    result: Any | None = None
    error: str | None = None
    started_at: Annotated[AwareDatetime, Field(alias="startedAt")]
    completed_at: Annotated[AwareDatetime | None, Field(alias="completedAt")] = None
    duration: Annotated[float | None, Field(ge=0.0)] = None


class ActionExecutionSearchResult(WireModel):
    """
    Wire model for OpenAPI component ActionExecutionSearchResultResponseDto.
    """

    items: list[ActionExecutionSearchResultItem]
    pagination: ActionExecutionSearchResultPagination


class ActionExecutionSearchResultItem(WireModel):
    """
    Inline object hoisted from ActionExecutionSearchResult.items[].
    """

    id: Annotated[str, Field(min_length=1)]
    definition_id: Annotated[str | None, Field(alias="definitionId")]
    device_id: Annotated[str | None, Field(alias="deviceId")]
    component_id: Annotated[str | None, Field(alias="componentId")]
    parameters: dict[str, Any]
    source: Annotated[str, Field(min_length=1)]
    source_id: Annotated[str | None, Field(alias="sourceId")]
    status: str
    result: Annotated[dict[str, Any] | None, Field(...)]
    error: Annotated[str | None, Field(...)]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    executed_at: Annotated[AwareDatetime, Field(alias="executedAt")]
    completed_at: Annotated[AwareDatetime | None, Field(alias="completedAt")]
    duration: Annotated[int | None, Field(ge=-9007199254740991, le=9007199254740991)]
    capture_session_id: Annotated[str | None, Field(alias="captureSessionId")]


class ActionExecutionSearchResultPagination(WireModel):
    """
    Inline object hoisted from ActionExecutionSearchResult.pagination.
    """

    page: Annotated[int, Field(ge=1, le=9007199254740991)]
    limit: Annotated[int, Field(ge=1, le=9007199254740991)]
    total: Annotated[int, Field(ge=0, le=9007199254740991)]
    total_pages: Annotated[int, Field(alias="totalPages", ge=0, le=9007199254740991)]
    has_next: Annotated[bool, Field(alias="hasNext")]
    has_prev: Annotated[bool, Field(alias="hasPrev")]


class ActionExecutionStatusError(WireModel):
    """
    Inline object hoisted from ActionExecutionStatus.<anyOf:Error>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    error: str


class ActionExecutionStatusResultCache(WireModel):
    """
    Inline object hoisted from ActionExecutionStatus.<anyOf:Result>.<oneOf:Cache>.
    """

    execution_id: Annotated[str, Field(alias="executionId")]
    action_def_id: Annotated[str, Field(alias="actionDefId")]
    status: str
    result: Any | None = None
    error: str | None = None
    started_at: Annotated[AwareDatetime, Field(alias="startedAt")]
    completed_at: Annotated[AwareDatetime | None, Field(alias="completedAt")] = None
    duration: Annotated[float | None, Field(ge=0.0)] = None
    retrieved_from: Annotated[str, Field(alias="retrievedFrom")]


class ActionExecutionStatusResultDb(WireModel):
    """
    Inline object hoisted from ActionExecutionStatus.<anyOf:Result>.<oneOf:Db>.
    """

    execution_id: Annotated[str, Field(alias="executionId")]
    action_def_id: Annotated[str | None, Field(alias="actionDefId")]
    status: str
    result: Any | None = None
    error: str | None = None
    started_at: Annotated[AwareDatetime, Field(alias="startedAt")]
    completed_at: Annotated[AwareDatetime | None, Field(alias="completedAt")] = None
    duration: Annotated[float | None, Field(ge=0.0)] = None
    retrieved_from: Annotated[str, Field(alias="retrievedFrom")]


class ActionExecutionStatus(
    RootModel[ActionExecutionStatusResultCache | ActionExecutionStatusResultDb | ActionExecutionStatusError]
):
    root: Annotated[
        ActionExecutionStatusResultCache | ActionExecutionStatusResultDb | ActionExecutionStatusError,
        Field(description="Wire model for OpenAPI component ActionExecutionStatusHttpResponseDto."),
    ]


class Agent(WireModel):
    """
    Untyped in the committed OpenAPI artifact: ManagementAgentsController_create declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class AgentCaptureSession(WireModel):
    """
    Untyped in the committed OpenAPI artifact: AgentMediaController_createCaptureSession declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class AgentImageUpload(WireModel):
    """
    Untyped in the committed OpenAPI artifact: AgentMediaController_uploadImage declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class AgentImageUploadComplete(WireModel):
    """
    Untyped in the committed OpenAPI artifact: AgentMediaController_completeImageUpload declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class ArtifactDownload(WireModel):
    """
    Wire model for OpenAPI component OpenArtifactResponseDto.
    """

    artifact_id: Annotated[str, Field(alias="artifactId")]
    download_url: Annotated[str, Field(alias="downloadUrl")]
    expires_at: Annotated[AwareDatetime, Field(alias="expiresAt")]


class BandProvenance(WireModel):
    """
    Wire model for OpenAPI component BandProvenanceLookupResponseDto.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    band_registration: Annotated[
        BandProvenanceBandRegistrationUnknown
        | BandProvenanceBandRegistrationUnregistered
        | BandProvenanceBandRegistrationRegisteredProcessedProduct
        | BandProvenanceBandRegistrationRegisteredCameraMetadata
        | BandProvenanceBandRegistrationRegisteredManualProfile,
        Field(alias="bandRegistration"),
    ]
    normalization: Annotated[BandProvenanceNormalization | None, Field(...)]
    band_interpretation: Annotated[BandProvenanceBandInterpretation, Field(alias="bandInterpretation")]
    zarr_seal: Annotated[BandProvenanceZarrSeal, Field(alias="zarrSeal")]


class BandProvenanceBandInterpretation(WireModel):
    """
    Inline object hoisted from BandProvenance.bandInterpretation.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Literal[1]
    layout: str
    bands: Annotated[
        list[
            BandProvenanceBandInterpretationBandVerifiedMetadata
            | BandProvenanceBandInterpretationBandApprovedProfile
            | BandProvenanceBandInterpretationBandUserConfirmed
            | BandProvenanceBandInterpretationBandUnresolved
        ],
        Field(min_length=1),
    ]


class BandProvenanceBandInterpretationBandApprovedProfile(WireModel):
    """
    Inline object hoisted from BandProvenance.bandInterpretation.bands[].<oneOf:ApprovedProfile>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    band_id: Annotated[str, Field(alias="bandId", pattern="^[a-z][a-z0-9_]{0,31}$")]
    evidence: str
    basis: BandProvenanceBandInterpretationBandApprovedProfileBasis


class BandProvenanceBandInterpretationBandApprovedProfileBasis(WireModel):
    """
    Inline object hoisted from BandProvenance.bandInterpretation.bands[].<oneOf:ApprovedProfile>.basis.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    device_id: Annotated[str, Field(alias="deviceId", min_length=1)]
    profile_key: Annotated[str, Field(alias="profileKey", min_length=1)]
    revision: Annotated[str, Field(min_length=1)]


class BandProvenanceBandInterpretationBandUnresolved(WireModel):
    """
    Inline object hoisted from BandProvenance.bandInterpretation.bands[].<oneOf:Unresolved>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    band_id: Annotated[str, Field(alias="bandId", pattern="^[a-z][a-z0-9_]{0,31}$")]
    evidence: str
    basis: Any


class BandProvenanceBandInterpretationBandUserConfirmed(WireModel):
    """
    Inline object hoisted from BandProvenance.bandInterpretation.bands[].<oneOf:UserConfirmed>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    band_id: Annotated[str, Field(alias="bandId", pattern="^[a-z][a-z0-9_]{0,31}$")]
    evidence: str
    basis: Any


class BandProvenanceBandInterpretationBandVerifiedMetadata(WireModel):
    """
    Inline object hoisted from BandProvenance.bandInterpretation.bands[].<oneOf:VerifiedMetadata>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    band_id: Annotated[str, Field(alias="bandId", pattern="^[a-z][a-z0-9_]{0,31}$")]
    evidence: str
    basis: BandProvenanceBandInterpretationBandVerifiedMetadataBasis


class BandProvenanceBandInterpretationBandVerifiedMetadataBasis(WireModel):
    """
    Inline object hoisted from BandProvenance.bandInterpretation.bands[].<oneOf:VerifiedMetadata>.basis.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    file_id: Annotated[str, Field(alias="fileId")]
    content_sha256: Annotated[str, Field(alias="contentSha256", pattern="^sha256:[0-9a-f]{64}$")]
    fields: Annotated[list[str], Field(min_length=1)]


class BandProvenanceBandRegistrationRegisteredCameraMetadata(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:CameraMetadata>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    reference_band_id: Annotated[str, Field(alias="referenceBandId", pattern="^[a-z][a-z0-9_]{0,31}$")]
    grid: BandProvenanceBandRegistrationRegisteredCameraMetadataGrid
    resampling: str
    valid_region: Annotated[list[int], Field(alias="validRegion", max_length=4, min_length=4)]
    path: str
    derived_from: Annotated[str, Field(alias="derivedFrom")]
    aligner: BandProvenanceBandRegistrationRegisteredCameraMetadataAligner
    transforms: Annotated[
        list[BandProvenanceBandRegistrationRegisteredCameraMetadataTransform],
        Field(min_length=1),
    ]
    version: Literal[1]
    layout: str
    recorded_by: Annotated[
        BandProvenanceBandRegistrationRegisteredCameraMetadataRecordedBy,
        Field(alias="recordedBy"),
    ]
    recorded_at: Annotated[AwareDatetime, Field(alias="recordedAt")]
    state: str


class BandProvenanceBandRegistrationRegisteredCameraMetadataAligner(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:CameraMetadata>.aligner.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    operation: Annotated[str, Field(min_length=1)]
    policy_version: Annotated[str, Field(alias="policyVersion", min_length=1)]


class BandProvenanceBandRegistrationRegisteredCameraMetadataGrid(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:CameraMetadata>.grid.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    shape: Annotated[list[int], Field(max_length=2, min_length=2)]
    transform: Annotated[list[float], Field(max_length=6, min_length=6)]


class BandProvenanceBandRegistrationRegisteredCameraMetadataRecordedBy(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:CameraMetadata>.recordedBy.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    id: Annotated[str, Field(min_length=1)]


class BandProvenanceBandRegistrationRegisteredCameraMetadataTransform(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:CameraMetadata>.transforms[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    band_id: Annotated[str, Field(alias="bandId", pattern="^[a-z][a-z0-9_]{0,31}$")]
    matrix: Annotated[list[float], Field(max_length=9, min_length=9)]


class BandProvenanceBandRegistrationRegisteredManualProfile(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    reference_band_id: Annotated[str, Field(alias="referenceBandId", pattern="^[a-z][a-z0-9_]{0,31}$")]
    grid: BandProvenanceBandRegistrationRegisteredManualProfileGrid
    resampling: str
    valid_region: Annotated[list[int], Field(alias="validRegion", max_length=4, min_length=4)]
    path: str
    derived_from: Annotated[str, Field(alias="derivedFrom")]
    aligner: BandProvenanceBandRegistrationRegisteredManualProfileAligner
    transforms: Annotated[
        list[BandProvenanceBandRegistrationRegisteredManualProfileTransform],
        Field(min_length=1),
    ]
    profile: BandProvenanceBandRegistrationRegisteredManualProfileProfile
    version: Literal[1]
    layout: str
    recorded_by: Annotated[
        BandProvenanceBandRegistrationRegisteredManualProfileRecordedBy,
        Field(alias="recordedBy"),
    ]
    recorded_at: Annotated[AwareDatetime, Field(alias="recordedAt")]
    state: str


class BandProvenanceBandRegistrationRegisteredManualProfileAligner(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.aligner.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    operation: Annotated[str, Field(min_length=1)]
    policy_version: Annotated[str, Field(alias="policyVersion", min_length=1)]


class BandProvenanceBandRegistrationRegisteredManualProfileGrid(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.grid.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    shape: Annotated[list[int], Field(max_length=2, min_length=2)]
    transform: Annotated[list[float], Field(max_length=6, min_length=6)]


class BandProvenanceBandRegistrationRegisteredManualProfileProfile(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.profile.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    device_id: Annotated[str, Field(alias="deviceId", min_length=1)]
    profile_key: Annotated[str, Field(alias="profileKey", min_length=1)]
    revision: Annotated[str, Field(min_length=1)]


class BandProvenanceBandRegistrationRegisteredManualProfileRecordedBy(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.recordedBy.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    id: Annotated[str, Field(min_length=1)]


class BandProvenanceBandRegistrationRegisteredManualProfileTransform(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ManualProfile>.transforms[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    band_id: Annotated[str, Field(alias="bandId", pattern="^[a-z][a-z0-9_]{0,31}$")]
    matrix: Annotated[list[float], Field(max_length=9, min_length=9)]


class BandProvenanceBandRegistrationRegisteredProcessedProduct(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ProcessedProduct>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    reference_band_id: Annotated[str, Field(alias="referenceBandId", pattern="^[a-z][a-z0-9_]{0,31}$")]
    grid: BandProvenanceBandRegistrationRegisteredProcessedProductGrid
    resampling: str
    valid_region: Annotated[list[int], Field(alias="validRegion", max_length=4, min_length=4)]
    path: str
    lineage: Annotated[str, Field(max_length=1024, min_length=1)]
    version: Literal[1]
    layout: str
    recorded_by: Annotated[
        BandProvenanceBandRegistrationRegisteredProcessedProductRecordedBy,
        Field(alias="recordedBy"),
    ]
    recorded_at: Annotated[AwareDatetime, Field(alias="recordedAt")]
    state: str


class BandProvenanceBandRegistrationRegisteredProcessedProductGrid(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ProcessedProduct>.grid.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    shape: Annotated[list[int], Field(max_length=2, min_length=2)]
    transform: Annotated[list[float], Field(max_length=6, min_length=6)]


class BandProvenanceBandRegistrationRegisteredProcessedProductRecordedBy(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Registered>.<oneOf:ProcessedProduct>.recordedBy.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    id: Annotated[str, Field(min_length=1)]


class BandProvenanceBandRegistrationUnknown(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Unknown>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Literal[1]
    layout: str
    recorded_by: Annotated[BandProvenanceBandRegistrationUnknownRecordedBy, Field(alias="recordedBy")]
    recorded_at: Annotated[AwareDatetime, Field(alias="recordedAt")]
    state: str


class BandProvenanceBandRegistrationUnknownRecordedBy(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Unknown>.recordedBy.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    id: Annotated[str, Field(min_length=1)]


class BandProvenanceBandRegistrationUnregistered(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Unregistered>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Literal[1]
    layout: str
    recorded_by: Annotated[BandProvenanceBandRegistrationUnregisteredRecordedBy, Field(alias="recordedBy")]
    recorded_at: Annotated[AwareDatetime, Field(alias="recordedAt")]
    state: str


class BandProvenanceBandRegistrationUnregisteredRecordedBy(WireModel):
    """
    Inline object hoisted from BandProvenance.bandRegistration.<anyOf:Unregistered>.recordedBy.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    id: Annotated[str, Field(min_length=1)]


class BandProvenanceNormalization(WireModel):
    """
    Inline object hoisted from BandProvenance.normalization.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    ref: BandProvenanceNormalizationRef
    record: BandProvenanceNormalizationRecord


class BandProvenanceNormalizationRecord(WireModel):
    """
    Inline object hoisted from BandProvenance.normalization.record.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Literal[1]
    sources: Annotated[
        list[BandProvenanceNormalizationRecordSourceFile | BandProvenanceNormalizationRecordSourceDeviceProfile],
        Field(min_length=1),
    ]
    converter: BandProvenanceNormalizationRecordConverter
    processing_level: Annotated[str, Field(alias="processingLevel")]
    unit_conversions: Annotated[list[dict[str, Any]], Field(alias="unitConversions")]
    saturation: dict[str, Any]
    missing: dict[str, Any]
    calibration_table_sha256: Annotated[
        str | None,
        Field(alias="calibrationTableSha256", pattern="^sha256:[0-9a-f]{64}$"),
    ] = None
    layout: str


class BandProvenanceNormalizationRecordConverter(WireModel):
    """
    Inline object hoisted from BandProvenance.normalization.record.converter.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    operation: Annotated[str, Field(min_length=1)]
    policy_version: Annotated[str, Field(alias="policyVersion", min_length=1)]


class BandProvenanceNormalizationRecordSourceDeviceProfile(WireModel):
    """
    Inline object hoisted from BandProvenance.normalization.record.sources[].<oneOf:DeviceProfile>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    device_id: Annotated[str, Field(alias="deviceId", min_length=1)]
    profile_key: Annotated[str, Field(alias="profileKey", min_length=1)]
    revision: Annotated[str, Field(min_length=1)]


class BandProvenanceNormalizationRecordSourceFile(WireModel):
    """
    Inline object hoisted from BandProvenance.normalization.record.sources[].<oneOf:File>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    file_id: Annotated[str, Field(alias="fileId")]
    content_sha256: Annotated[str, Field(alias="contentSha256", pattern="^sha256:[0-9a-f]{64}$")]
    byte_size: Annotated[int, Field(alias="byteSize", ge=0, le=9007199254740991)]
    bands: Annotated[list[BandProvenanceNormalizationRecordSourceFileBand], Field(min_length=1)]


class BandProvenanceNormalizationRecordSourceFileBand(WireModel):
    """
    Inline object hoisted from BandProvenance.normalization.record.sources[].<oneOf:File>.bands[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    band_id: Annotated[str, Field(alias="bandId", pattern="^[a-z][a-z0-9_]{0,31}$")]
    page: Annotated[int | None, Field(ge=0, le=9007199254740991)] = None
    sample: Annotated[int | None, Field(ge=0, le=9007199254740991)] = None


class BandProvenanceNormalizationRef(WireModel):
    """
    Inline object hoisted from BandProvenance.normalization.ref.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Literal[1]
    sha256: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]


class BandProvenanceZarrSeal(WireModel):
    """
    Inline object hoisted from BandProvenance.zarrSeal.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    digest: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    members: list[BandProvenanceZarrSealMember]


class BandProvenanceZarrSealMember(WireModel):
    """
    Inline object hoisted from BandProvenance.zarrSeal.members[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    key: Annotated[str, Field(min_length=1)]
    size: Annotated[int, Field(ge=0, le=9007199254740991)]


class CaptureSession(WireModel):
    """
    Wire model for OpenAPI component CaptureSessionWithMediaResponseDto.
    """

    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str | None, Field(...)]
    trigger_source: Annotated[str, Field(alias="triggerSource")]
    triggered_by: Annotated[str | None, Field(alias="triggeredBy")]
    triggered_action_id: Annotated[str | None, Field(alias="triggeredActionId")]
    triggered_action_execution_id: Annotated[str | None, Field(alias="triggeredActionExecutionId")]
    spot_id: Annotated[str | None, Field(alias="spotId")]
    device_id: Annotated[str | None, Field(alias="deviceId")]
    capture_group: Annotated[str, Field(alias="captureGroup")]
    session_group_id: Annotated[str | None, Field(alias="sessionGroupId")]
    identity_label_keys: Annotated[list[str] | None, Field(alias="identityLabelKeys")] = None
    status: str
    planned_at: Annotated[AwareDatetime | None, Field(alias="plannedAt")]
    started_at: Annotated[AwareDatetime | None, Field(alias="startedAt")]
    completed_at: Annotated[AwareDatetime | None, Field(alias="completedAt")]
    progress_status: Annotated[str | None, Field(alias="progressStatus")]
    progress_percentage: Annotated[int | None, Field(alias="progressPercentage", ge=0, le=100)]
    progress_details: Annotated[dict[str, Any] | None, Field(alias="progressDetails")]
    parameters: Annotated[dict[str, Any] | None, Field(...)]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    media_asset_count: Annotated[int, Field(alias="mediaAssetCount", ge=0, le=9007199254740991)]
    modalities_captured: Annotated[list[str], Field(alias="modalitiesCaptured")]
    annotation_count: Annotated[int, Field(alias="annotationCount", ge=0, le=9007199254740991)]
    session_group_member_count: Annotated[
        int | None, Field(alias="sessionGroupMemberCount", ge=0, le=9007199254740991)
    ] = None
    media: list[CaptureSessionMedia]
    tags: list[CaptureSessionTag]
    spot: CaptureSessionSpot | None = None


class CaptureSessionDetail(WireModel):
    """
    Wire model for OpenAPI component CaptureSessionDetailResponseDto.
    """

    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str | None, Field(...)]
    trigger_source: Annotated[str, Field(alias="triggerSource")]
    triggered_by: Annotated[str | None, Field(alias="triggeredBy")]
    triggered_action_id: Annotated[str | None, Field(alias="triggeredActionId")]
    triggered_action_execution_id: Annotated[str | None, Field(alias="triggeredActionExecutionId")]
    spot_id: Annotated[str | None, Field(alias="spotId")]
    device_id: Annotated[str | None, Field(alias="deviceId")]
    capture_group: Annotated[str, Field(alias="captureGroup")]
    session_group_id: Annotated[str | None, Field(alias="sessionGroupId")]
    identity_label_keys: Annotated[list[str] | None, Field(alias="identityLabelKeys")] = None
    status: str
    planned_at: Annotated[AwareDatetime | None, Field(alias="plannedAt")]
    started_at: Annotated[AwareDatetime | None, Field(alias="startedAt")]
    completed_at: Annotated[AwareDatetime | None, Field(alias="completedAt")]
    progress_status: Annotated[str | None, Field(alias="progressStatus")]
    progress_percentage: Annotated[int | None, Field(alias="progressPercentage", ge=0, le=100)]
    progress_details: Annotated[dict[str, Any] | None, Field(alias="progressDetails")]
    parameters: Annotated[dict[str, Any] | None, Field(...)]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    media_asset_count: Annotated[int, Field(alias="mediaAssetCount", ge=0, le=9007199254740991)]
    modalities_captured: Annotated[list[str], Field(alias="modalitiesCaptured")]
    spot: Annotated[CaptureSessionDetailSpot | None, Field(...)]
    device: Annotated[CaptureSessionDetailDevice | None, Field(...)]
    media: list[CaptureSessionDetailMedia]


class CaptureSessionDetailDevice(WireModel):
    """
    Inline object hoisted from CaptureSessionDetail.device.
    """

    id: str
    name: str
    identifier: str


class CaptureSessionDetailMedia(WireModel):
    """
    Inline object hoisted from CaptureSessionDetail.media[].
    """

    id: Annotated[str, Field(min_length=1)]
    file_id: Annotated[str, Field(alias="fileId")]
    thumbnail_file_id: Annotated[str | None, Field(alias="thumbnailFileId")]
    image_url: Annotated[str, Field(alias="imageUrl")]
    thumbnail_url: Annotated[str | None, Field(alias="thumbnailUrl")]
    format: Annotated[str | None, Field(...)]
    modality: str
    capture_session_id: Annotated[str, Field(alias="captureSessionId", min_length=1)]
    capture_session_name: Annotated[str | None, Field(alias="captureSessionName")] = None
    spot_id: Annotated[str | None, Field(alias="spotId")]
    device_id: Annotated[str | None, Field(alias="deviceId")]
    component_id: Annotated[str | None, Field(alias="componentId")]
    labels: dict[str, str] | None = None
    identity_tuple: Annotated[dict[str, str] | None, Field(alias="identityTuple")] = None
    provenance: CaptureSessionDetailMediaProvenance | None = None
    sensor_model: Annotated[str | None, Field(alias="sensorModel")] = None
    sensor_serial: Annotated[str | None, Field(alias="sensorSerial")] = None
    width: Annotated[int | None, Field(ge=-9007199254740991, le=9007199254740991)]
    height: Annotated[int | None, Field(ge=-9007199254740991, le=9007199254740991)]
    resolution: Annotated[str | None, Field(...)]
    capture_parameters: Annotated[dict[str, Any] | None, Field(alias="captureParameters")]
    quality_metrics: Annotated[dict[str, Any] | None, Field(alias="qualityMetrics")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    original: CaptureSessionDetailMediaOriginal | None = None
    captured_at: Annotated[AwareDatetime | None, Field(alias="capturedAt")]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]


class CaptureSessionDetailMediaOriginal(WireModel):
    """
    Inline object hoisted from CaptureSessionDetail.media[].original.
    """

    file_id: Annotated[str, Field(alias="fileId")]
    same_size: Annotated[bool, Field(alias="sameSize")]


class CaptureSessionDetailMediaProvenance(WireModel):
    """
    Inline object hoisted from CaptureSessionDetail.media[].provenance.
    """

    actor: CaptureSessionDetailMediaProvenanceActor
    source_asset_ids: Annotated[list[str], Field(alias="sourceAssetIds")]
    reserved_at: Annotated[AwareDatetime, Field(alias="reservedAt")]
    completed_at: Annotated[AwareDatetime | None, Field(alias="completedAt")] = None


class CaptureSessionDetailMediaProvenanceActor(WireModel):
    """
    Inline object hoisted from CaptureSessionDetail.media[].provenance.actor.
    """

    type: str
    id: str


class CaptureSessionDetailSpot(WireModel):
    """
    Inline object hoisted from CaptureSessionDetail.spot.
    """

    id: str
    name: str
    slug: str


class CaptureSessionMedia(WireModel):
    """
    Inline object hoisted from CaptureSession.media[].
    """

    id: Annotated[str, Field(min_length=1)]
    file_id: Annotated[str, Field(alias="fileId")]
    thumbnail_file_id: Annotated[str | None, Field(alias="thumbnailFileId")]
    image_url: Annotated[str, Field(alias="imageUrl")]
    thumbnail_url: Annotated[str | None, Field(alias="thumbnailUrl")]
    format: Annotated[str | None, Field(...)]
    modality: str
    capture_session_id: Annotated[str, Field(alias="captureSessionId", min_length=1)]
    capture_session_name: Annotated[str | None, Field(alias="captureSessionName")] = None
    spot_id: Annotated[str | None, Field(alias="spotId")]
    device_id: Annotated[str | None, Field(alias="deviceId")]
    component_id: Annotated[str | None, Field(alias="componentId")]
    labels: dict[str, str] | None = None
    identity_tuple: Annotated[dict[str, str] | None, Field(alias="identityTuple")] = None
    provenance: CaptureSessionMediaProvenance | None = None
    sensor_model: Annotated[str | None, Field(alias="sensorModel")] = None
    sensor_serial: Annotated[str | None, Field(alias="sensorSerial")] = None
    width: Annotated[int | None, Field(ge=-9007199254740991, le=9007199254740991)]
    height: Annotated[int | None, Field(ge=-9007199254740991, le=9007199254740991)]
    resolution: Annotated[str | None, Field(...)]
    capture_parameters: Annotated[dict[str, Any] | None, Field(alias="captureParameters")]
    quality_metrics: Annotated[dict[str, Any] | None, Field(alias="qualityMetrics")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    original: CaptureSessionMediaOriginal | None = None
    captured_at: Annotated[AwareDatetime | None, Field(alias="capturedAt")]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]


class CaptureSessionMediaOriginal(WireModel):
    """
    Inline object hoisted from CaptureSession.media[].original.
    """

    file_id: Annotated[str, Field(alias="fileId")]
    same_size: Annotated[bool, Field(alias="sameSize")]


class CaptureSessionMediaProvenance(WireModel):
    """
    Inline object hoisted from CaptureSession.media[].provenance.
    """

    actor: CaptureSessionMediaProvenanceActor
    source_asset_ids: Annotated[list[str], Field(alias="sourceAssetIds")]
    reserved_at: Annotated[AwareDatetime, Field(alias="reservedAt")]
    completed_at: Annotated[AwareDatetime | None, Field(alias="completedAt")] = None


class CaptureSessionMediaProvenanceActor(WireModel):
    """
    Inline object hoisted from CaptureSession.media[].provenance.actor.
    """

    type: str
    id: str


class CaptureSessionSpot(WireModel):
    """
    Inline object hoisted from CaptureSession.spot.
    """

    id: str
    name: str
    slug: str


class CaptureSessionTag(WireModel):
    """
    Inline object hoisted from CaptureSession.tags[].
    """

    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    slug: Annotated[str, Field(min_length=1)]
    color: Annotated[str | None, Field(...)]
    icon: Annotated[str | None, Field(...)]
    description: Annotated[str | None, Field(...)]


class CompleteImageUploadResponse(WireModel):
    """
    Wire model for OpenAPI component CompleteImageUploadResponseDto.
    """

    media_asset_id: Annotated[str, Field(alias="mediaAssetId", min_length=1)]
    success: bool
    message: str


class Component(WireModel):
    """
    Untyped in the committed OpenAPI artifact: ComponentController_findAll declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class CreatedSpot(WireModel):
    """
    Untyped in the committed OpenAPI artifact: SpotsController_create declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class Device(WireModel):
    """
    Untyped in the committed OpenAPI artifact: DeviceController_findOne declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class DeviceRegistration(WireModel):
    """
    Untyped in the committed OpenAPI artifact: DeviceController_selfRegister declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class DeviceStatus(WireModel):
    """
    Untyped in the committed OpenAPI artifact: DeviceController_getStatus declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


type FixedAxisIndicesAdditionalProperty = Annotated[int, Field(ge=0, le=9007199254740991)]


class ManualActionDryRun(WireModel):
    """
    Wire model for OpenAPI component ManualActionDryRunResponseDto.
    """

    dry_run: Annotated[Literal[True], Field(alias="dryRun")]
    action_def_id: Annotated[str, Field(alias="actionDefId")]
    device_id: Annotated[str, Field(alias="deviceId")]
    params: dict[str, Any]
    checks: ManualActionDryRunChecks


class ManualActionDryRunChecks(WireModel):
    """
    Inline object hoisted from ManualActionDryRun.checks.
    """

    definition: ManualActionDryRunChecksDefinition
    scope: ManualActionDryRunChecksScope
    schema_: Annotated[ManualActionDryRunChecksSchema, Field(alias="schema")]
    online: ManualActionDryRunChecksOnline
    conflict: ManualActionDryRunChecksConflict


class ManualActionDryRunChecksConflict(WireModel):
    """
    Inline object hoisted from ManualActionDryRun.checks.conflict.
    """

    verdict: str
    reason: str | None = None


class ManualActionDryRunChecksDefinition(WireModel):
    """
    Inline object hoisted from ManualActionDryRun.checks.definition.
    """

    verdict: str
    reason: str | None = None


class ManualActionDryRunChecksOnline(WireModel):
    """
    Inline object hoisted from ManualActionDryRun.checks.online.
    """

    verdict: str
    reason: str | None = None


class ManualActionDryRunChecksSchema(WireModel):
    """
    Inline object hoisted from ManualActionDryRun.checks.schema.
    """

    verdict: str
    reason: str | None = None


class ManualActionDryRunChecksScope(WireModel):
    """
    Inline object hoisted from ManualActionDryRun.checks.scope.
    """

    verdict: str
    reason: str | None = None


class ManualActionExecution(WireModel):
    """
    Wire model for OpenAPI component ManualActionExecutionResponseDto.
    """

    execution_id: Annotated[str, Field(alias="executionId", description="Created ActionExecution ID")]
    action_def_id: Annotated[str, Field(alias="actionDefId", description="ActionDefinition ID")]
    device_id: Annotated[str, Field(alias="deviceId", description="Target device ID")]
    status: Annotated[str, Field(description="Current execution status")]
    mqtt_published: Annotated[
        bool,
        Field(
            alias="mqttPublished",
            description="Whether the broker accepted the ActionCommand (QoS 1 PUBACK). true = broker acknowledged; does NOT confirm agent-rs received the command. false = publish call failed or was skipped (idempotent replay). Use ActionResult on agents/{agentId}/results as the authoritative delivery signal.",
        ),
    ]
    timestamp: Annotated[AwareDatetime, Field(description="ISO 8601 timestamp when command was issued")]


class MediaAsset(WireModel):
    """
    Wire model for OpenAPI component MediaAssetResponseDto.
    """

    id: Annotated[str, Field(min_length=1)]
    file_id: Annotated[str, Field(alias="fileId")]
    thumbnail_file_id: Annotated[str | None, Field(alias="thumbnailFileId")]
    image_url: Annotated[str, Field(alias="imageUrl")]
    thumbnail_url: Annotated[str | None, Field(alias="thumbnailUrl")]
    format: Annotated[str | None, Field(...)]
    modality: str
    capture_session_id: Annotated[str, Field(alias="captureSessionId", min_length=1)]
    capture_session_name: Annotated[str | None, Field(alias="captureSessionName")] = None
    spot_id: Annotated[str | None, Field(alias="spotId")]
    device_id: Annotated[str | None, Field(alias="deviceId")]
    component_id: Annotated[str | None, Field(alias="componentId")]
    labels: dict[str, str] | None = None
    identity_tuple: Annotated[dict[str, str] | None, Field(alias="identityTuple")] = None
    provenance: MediaAssetProvenance | None = None
    sensor_model: Annotated[str | None, Field(alias="sensorModel")] = None
    sensor_serial: Annotated[str | None, Field(alias="sensorSerial")] = None
    width: Annotated[int | None, Field(ge=-9007199254740991, le=9007199254740991)]
    height: Annotated[int | None, Field(ge=-9007199254740991, le=9007199254740991)]
    resolution: Annotated[str | None, Field(...)]
    capture_parameters: Annotated[dict[str, Any] | None, Field(alias="captureParameters")]
    quality_metrics: Annotated[dict[str, Any] | None, Field(alias="qualityMetrics")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    original: MediaAssetOriginal | None = None
    captured_at: Annotated[AwareDatetime | None, Field(alias="capturedAt")]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]


class MediaAssetOriginal(WireModel):
    """
    Inline object hoisted from MediaAsset.original.
    """

    file_id: Annotated[str, Field(alias="fileId")]
    same_size: Annotated[bool, Field(alias="sameSize")]


class MediaAssetPresignedUrl(WireModel):
    """
    Wire model for OpenAPI component MediaAssetPresignedUrlResponseDto.
    """

    url: str
    expires_in: Annotated[int, Field(alias="expiresIn", gt=0, le=9007199254740991)]


class MediaAssetProvenance(WireModel):
    """
    Inline object hoisted from MediaAsset.provenance.
    """

    actor: MediaAssetProvenanceActor
    source_asset_ids: Annotated[list[str], Field(alias="sourceAssetIds")]
    reserved_at: Annotated[AwareDatetime, Field(alias="reservedAt")]
    completed_at: Annotated[AwareDatetime | None, Field(alias="completedAt")] = None


class MediaAssetProvenanceActor(WireModel):
    """
    Inline object hoisted from MediaAsset.provenance.actor.
    """

    type: str
    id: str


type MemberSizesAdditionalProperty = Annotated[int, Field(ge=0, le=9007199254740991)]


class Organization(WireModel):
    """
    Wire model for OpenAPI component OrganizationResponseDto.
    """

    id: str
    name: Annotated[str, Field(max_length=255, min_length=1)]
    slug: Annotated[str, Field(max_length=50, min_length=3, pattern="^[a-z0-9-]+$")]
    status: str
    metadata: dict[str, Any] | None = None
    logo_url: Annotated[str | None, Field(alias="logoUrl")] = None
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")] = None
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]


class PhenosSession(WireModel):
    """
    Wire model for OpenAPI component ExternalToolGatewaySessionDto.
    """

    session_id: Annotated[str, Field(alias="sessionId")]
    organization_id: Annotated[str, Field(alias="organizationId", min_length=1)]
    user_id: Annotated[str, Field(alias="userId", min_length=1)]
    client_name: Annotated[str, Field(alias="clientName", max_length=64, min_length=1)]
    references: PhenosSessionReferences
    operations: Annotated[list[str], Field(min_length=1)]
    status: str
    tool_calls_started: Annotated[int, Field(alias="toolCallsStarted", ge=0, le=9007199254740991)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    expires_at: Annotated[AwareDatetime, Field(alias="expiresAt")]
    sandbox_deadline_at: Annotated[AwareDatetime | None, Field(alias="sandboxDeadlineAt")]


class PhenosSessionCreation(WireModel):
    """
    Wire model for OpenAPI component CreateExternalToolGatewaySessionResponseDto.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    session: PhenosSessionCreationSession
    credential: PhenosSessionCreationCredential


class PhenosSessionCreationCredential(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.credential.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    token: Annotated[str, Field(min_length=1)]
    expires_at: Annotated[AwareDatetime, Field(alias="expiresAt")]


class PhenosSessionCreationSession(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.
    """

    session_id: Annotated[str, Field(alias="sessionId")]
    organization_id: Annotated[str, Field(alias="organizationId", min_length=1)]
    user_id: Annotated[str, Field(alias="userId", min_length=1)]
    client_name: Annotated[str, Field(alias="clientName", max_length=64, min_length=1)]
    references: PhenosSessionCreationSessionReferences
    operations: Annotated[list[str], Field(min_length=1)]
    status: str
    tool_calls_started: Annotated[int, Field(alias="toolCallsStarted", ge=0, le=9007199254740991)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    expires_at: Annotated[AwareDatetime, Field(alias="expiresAt")]
    sandbox_deadline_at: Annotated[AwareDatetime | None, Field(alias="sandboxDeadlineAt")]


class PhenosSessionCreationSessionReferences(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.
    """

    image: PhenosSessionCreationSessionReferencesImage
    annotations: Annotated[list[PhenosSessionCreationSessionReferencesAnnotation], Field(max_length=3)]


class PhenosSessionCreationSessionReferencesAnnotation(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.annotations[].
    """

    id: str
    revision: Annotated[int, Field(ge=0, le=9007199254740991)]
    geometry_fingerprint: Annotated[str, Field(alias="geometryFingerprint", pattern="^sha256:[0-9a-f]{64}$")]


class PhenosSessionCreationSessionReferencesImage(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.
    """

    id: str
    revision: Annotated[str, Field(max_length=128, min_length=1)]
    source_binding: Annotated[
        PhenosSessionCreationSessionReferencesImageSourceBinding | None,
        Field(alias="sourceBinding"),
    ] = None


class PhenosSessionCreationSessionReferencesImageSourceBinding(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    source_id: Annotated[str, Field(alias="sourceId")]
    file_id: Annotated[str, Field(alias="fileId")]
    file_sha256: Annotated[str, Field(alias="fileSha256", pattern="^sha256:[0-9a-f]{64}$")]
    revision: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    plane: PhenosSessionCreationSessionReferencesImageSourceBindingPlane
    coordinate_system: Annotated[
        PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystem,
        Field(alias="coordinateSystem"),
    ]
    grid: (
        PhenosSessionCreationSessionReferencesImageSourceBindingGridExifApplied
        | PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlane
    )


class PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystem(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.
    """

    coordinate_system_id: Annotated[str, Field(alias="coordinateSystemId", min_length=1)]
    source_id: Annotated[str, Field(alias="sourceId", min_length=1)]
    source_revision: Annotated[str, Field(alias="sourceRevision", min_length=1)]
    dimension_fingerprint: Annotated[str, Field(alias="dimensionFingerprint", pattern="^sha256:[0-9a-f]{64}$")]
    level: Literal[0]
    grid: str
    dimensions: PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemDimensions
    axes: PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxes
    pixel_origin: Annotated[
        PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemPixelOrigin,
        Field(alias="pixelOrigin"),
    ]
    angle_convention: Annotated[
        PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAngleConvention,
        Field(alias="angleConvention"),
    ]


class PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAngleConvention(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.angleConvention.
    """

    reference_axis: Annotated[str, Field(alias="referenceAxis")]
    positive_direction: Annotated[str, Field(alias="positiveDirection")]
    unit: str


class PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxes(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.axes.
    """

    x: PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxesX
    y: PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxesY


class PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxesX(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.axes.x.
    """

    name: Annotated[str, Field(min_length=1)]
    direction: str


class PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxesY(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.axes.y.
    """

    name: Annotated[str, Field(min_length=1)]
    direction: str


class PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemDimensions(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.dimensions.
    """

    width: Annotated[int, Field(gt=0, le=9007199254740991)]
    height: Annotated[int, Field(gt=0, le=9007199254740991)]


class PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemPixelOrigin(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.coordinateSystem.pixelOrigin.
    """

    corner: str
    sample_position: Annotated[str, Field(alias="samplePosition")]


class PhenosSessionCreationSessionReferencesImageSourceBindingGridExifApplied(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.grid.<oneOf:ExifApplied>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    stored_dimensions: Annotated[
        PhenosSessionCreationSessionReferencesImageSourceBindingGridExifAppliedStoredDimensions,
        Field(alias="storedDimensions"),
    ]
    orientation: Annotated[int, Field(ge=1, le=8)]


class PhenosSessionCreationSessionReferencesImageSourceBindingGridExifAppliedStoredDimensions(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.grid.<oneOf:ExifApplied>.storedDimensions.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    width: Annotated[int, Field(gt=0, le=9007199254740991)]
    height: Annotated[int, Field(gt=0, le=9007199254740991)]


class PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlane(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.grid.<oneOf:NativePlane>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    dataset_path: Annotated[str, Field(alias="datasetPath", max_length=1024, min_length=2, pattern="^\\/.*")]
    dimensions: PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlaneDimensions
    shape: Annotated[list[int], Field(max_length=16, min_length=2)]
    dtype: Annotated[str, Field(pattern="^[<>|]?[bhiuqefdBHIQ]\\d*$")]
    axes: Annotated[
        list[PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlaneAxe],
        Field(max_length=16, min_length=2),
    ]


class PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlaneAxe(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.grid.<oneOf:NativePlane>.axes[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(min_length=1)]
    direction: Annotated[str, Field(min_length=1)]
    cardinality: Annotated[int, Field(gt=0, le=9007199254740991)]


class PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlaneDimensions(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.grid.<oneOf:NativePlane>.dimensions.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    width: Annotated[int, Field(gt=0, le=9007199254740991)]
    height: Annotated[int, Field(gt=0, le=9007199254740991)]


class PhenosSessionCreationSessionReferencesImageSourceBindingPlane(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.plane.
    """

    coordinate_system_id: Annotated[str, Field(alias="coordinateSystemId", min_length=1)]
    source_revision: Annotated[str, Field(alias="sourceRevision", min_length=1)]
    dimension_fingerprint: Annotated[str, Field(alias="dimensionFingerprint", pattern="^sha256:[0-9a-f]{64}$")]
    level: Literal[0]
    axis_selection: Annotated[
        PhenosSessionCreationSessionReferencesImageSourceBindingPlaneAxisSelection,
        Field(alias="axisSelection"),
    ]


class PhenosSessionCreationSessionReferencesImageSourceBindingPlaneAxisSelection(WireModel):
    """
    Inline object hoisted from PhenosSessionCreation.session.references.image.sourceBinding.plane.axisSelection.
    """

    x_axis_name: Annotated[str, Field(alias="xAxisName", min_length=1)]
    y_axis_name: Annotated[str, Field(alias="yAxisName", min_length=1)]
    fixed_axis_indices: Annotated[dict[str, FixedAxisIndicesAdditionalProperty], Field(alias="fixedAxisIndices")]


class PhenosSessionReferences(WireModel):
    """
    Inline object hoisted from PhenosSession.references.
    """

    image: PhenosSessionReferencesImage
    annotations: Annotated[list[PhenosSessionReferencesAnnotation], Field(max_length=3)]


class PhenosSessionReferencesAnnotation(WireModel):
    """
    Inline object hoisted from PhenosSession.references.annotations[].
    """

    id: str
    revision: Annotated[int, Field(ge=0, le=9007199254740991)]
    geometry_fingerprint: Annotated[str, Field(alias="geometryFingerprint", pattern="^sha256:[0-9a-f]{64}$")]


class PhenosSessionReferencesImage(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.
    """

    id: str
    revision: Annotated[str, Field(max_length=128, min_length=1)]
    source_binding: Annotated[PhenosSessionReferencesImageSourceBinding | None, Field(alias="sourceBinding")] = None


class PhenosSessionReferencesImageSourceBinding(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    source_id: Annotated[str, Field(alias="sourceId")]
    file_id: Annotated[str, Field(alias="fileId")]
    file_sha256: Annotated[str, Field(alias="fileSha256", pattern="^sha256:[0-9a-f]{64}$")]
    revision: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    plane: PhenosSessionReferencesImageSourceBindingPlane
    coordinate_system: Annotated[
        PhenosSessionReferencesImageSourceBindingCoordinateSystem,
        Field(alias="coordinateSystem"),
    ]
    grid: (
        PhenosSessionReferencesImageSourceBindingGridExifApplied
        | PhenosSessionReferencesImageSourceBindingGridNativePlane
    )


class PhenosSessionReferencesImageSourceBindingCoordinateSystem(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.coordinateSystem.
    """

    coordinate_system_id: Annotated[str, Field(alias="coordinateSystemId", min_length=1)]
    source_id: Annotated[str, Field(alias="sourceId", min_length=1)]
    source_revision: Annotated[str, Field(alias="sourceRevision", min_length=1)]
    dimension_fingerprint: Annotated[str, Field(alias="dimensionFingerprint", pattern="^sha256:[0-9a-f]{64}$")]
    level: Literal[0]
    grid: str
    dimensions: PhenosSessionReferencesImageSourceBindingCoordinateSystemDimensions
    axes: PhenosSessionReferencesImageSourceBindingCoordinateSystemAxes
    pixel_origin: Annotated[
        PhenosSessionReferencesImageSourceBindingCoordinateSystemPixelOrigin,
        Field(alias="pixelOrigin"),
    ]
    angle_convention: Annotated[
        PhenosSessionReferencesImageSourceBindingCoordinateSystemAngleConvention,
        Field(alias="angleConvention"),
    ]


class PhenosSessionReferencesImageSourceBindingCoordinateSystemAngleConvention(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.coordinateSystem.angleConvention.
    """

    reference_axis: Annotated[str, Field(alias="referenceAxis")]
    positive_direction: Annotated[str, Field(alias="positiveDirection")]
    unit: str


class PhenosSessionReferencesImageSourceBindingCoordinateSystemAxes(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.coordinateSystem.axes.
    """

    x: PhenosSessionReferencesImageSourceBindingCoordinateSystemAxesX
    y: PhenosSessionReferencesImageSourceBindingCoordinateSystemAxesY


class PhenosSessionReferencesImageSourceBindingCoordinateSystemAxesX(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.coordinateSystem.axes.x.
    """

    name: Annotated[str, Field(min_length=1)]
    direction: str


class PhenosSessionReferencesImageSourceBindingCoordinateSystemAxesY(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.coordinateSystem.axes.y.
    """

    name: Annotated[str, Field(min_length=1)]
    direction: str


class PhenosSessionReferencesImageSourceBindingCoordinateSystemDimensions(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.coordinateSystem.dimensions.
    """

    width: Annotated[int, Field(gt=0, le=9007199254740991)]
    height: Annotated[int, Field(gt=0, le=9007199254740991)]


class PhenosSessionReferencesImageSourceBindingCoordinateSystemPixelOrigin(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.coordinateSystem.pixelOrigin.
    """

    corner: str
    sample_position: Annotated[str, Field(alias="samplePosition")]


class PhenosSessionReferencesImageSourceBindingGridExifApplied(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.grid.<oneOf:ExifApplied>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    stored_dimensions: Annotated[
        PhenosSessionReferencesImageSourceBindingGridExifAppliedStoredDimensions,
        Field(alias="storedDimensions"),
    ]
    orientation: Annotated[int, Field(ge=1, le=8)]


class PhenosSessionReferencesImageSourceBindingGridExifAppliedStoredDimensions(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.grid.<oneOf:ExifApplied>.storedDimensions.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    width: Annotated[int, Field(gt=0, le=9007199254740991)]
    height: Annotated[int, Field(gt=0, le=9007199254740991)]


class PhenosSessionReferencesImageSourceBindingGridNativePlane(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.grid.<oneOf:NativePlane>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    dataset_path: Annotated[str, Field(alias="datasetPath", max_length=1024, min_length=2, pattern="^\\/.*")]
    dimensions: PhenosSessionReferencesImageSourceBindingGridNativePlaneDimensions
    shape: Annotated[list[int], Field(max_length=16, min_length=2)]
    dtype: Annotated[str, Field(pattern="^[<>|]?[bhiuqefdBHIQ]\\d*$")]
    axes: Annotated[
        list[PhenosSessionReferencesImageSourceBindingGridNativePlaneAxe],
        Field(max_length=16, min_length=2),
    ]


class PhenosSessionReferencesImageSourceBindingGridNativePlaneAxe(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.grid.<oneOf:NativePlane>.axes[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(min_length=1)]
    direction: Annotated[str, Field(min_length=1)]
    cardinality: Annotated[int, Field(gt=0, le=9007199254740991)]


class PhenosSessionReferencesImageSourceBindingGridNativePlaneDimensions(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.grid.<oneOf:NativePlane>.dimensions.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    width: Annotated[int, Field(gt=0, le=9007199254740991)]
    height: Annotated[int, Field(gt=0, le=9007199254740991)]


class PhenosSessionReferencesImageSourceBindingPlane(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.plane.
    """

    coordinate_system_id: Annotated[str, Field(alias="coordinateSystemId", min_length=1)]
    source_revision: Annotated[str, Field(alias="sourceRevision", min_length=1)]
    dimension_fingerprint: Annotated[str, Field(alias="dimensionFingerprint", pattern="^sha256:[0-9a-f]{64}$")]
    level: Literal[0]
    axis_selection: Annotated[
        PhenosSessionReferencesImageSourceBindingPlaneAxisSelection,
        Field(alias="axisSelection"),
    ]


class PhenosSessionReferencesImageSourceBindingPlaneAxisSelection(WireModel):
    """
    Inline object hoisted from PhenosSession.references.image.sourceBinding.plane.axisSelection.
    """

    x_axis_name: Annotated[str, Field(alias="xAxisName", min_length=1)]
    y_axis_name: Annotated[str, Field(alias="yAxisName", min_length=1)]
    fixed_axis_indices: Annotated[dict[str, FixedAxisIndicesAdditionalProperty], Field(alias="fixedAxisIndices")]


class RecipeBatchCancel(WireModel):
    """
    Wire model for OpenAPI component RecipeBatchCancelResponseDto.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    cancelled: Annotated[int, Field(ge=0, le=9007199254740991)]


class RecipeBatchPage(WireModel):
    """
    Wire model for OpenAPI component RecipeBatchPageDto.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    batch_id: Annotated[str, Field(alias="batchId")]
    recipe_id: Annotated[str, Field(alias="recipeId")]
    recipe_version: Annotated[int, Field(alias="recipeVersion", gt=0, le=9007199254740991)]
    definition_fingerprint: Annotated[str, Field(alias="definitionFingerprint", pattern="^sha256:[0-9a-f]{64}$")]
    counts: RecipeBatchPageCounts
    partial: bool
    hidden_photos: Annotated[int, Field(alias="hiddenPhotos", ge=0, le=9007199254740991)]
    fingerprint: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    page: Annotated[int, Field(ge=0, le=9007199254740991)]
    next_page: Annotated[int | None, Field(alias="nextPage", gt=0, le=9007199254740991)]
    rows: list[RecipeBatchPageRow]


class RecipeBatchPageCounts(WireModel):
    """
    Inline object hoisted from RecipeBatchPage.counts.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    queued: Annotated[int, Field(ge=0, le=9007199254740991)]
    running: Annotated[int, Field(ge=0, le=9007199254740991)]
    succeeded: Annotated[int, Field(ge=0, le=9007199254740991)]
    blocked: Annotated[int, Field(ge=0, le=9007199254740991)]
    failed: Annotated[int, Field(ge=0, le=9007199254740991)]
    cancelled: Annotated[int, Field(ge=0, le=9007199254740991)]


class RecipeBatchPageRow(WireModel):
    """
    Inline object hoisted from RecipeBatchPage.rows[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    run_id: Annotated[str, Field(alias="runId")]
    image_id: Annotated[str, Field(alias="imageId")]
    file_id: Annotated[str | None, Field(alias="fileId")]
    photo_name: Annotated[str | None, Field(alias="photoName")]
    status: str
    failure_code: Annotated[str | None, Field(alias="failureCode")]
    step_id: Annotated[str | None, Field(alias="stepId")]
    operation_key: Annotated[str | None, Field(alias="operationKey")]
    annotation_id: Annotated[str | None, Field(alias="annotationId")]
    output_status: Annotated[str | None, Field(alias="outputStatus")]
    unavailable_reason: Annotated[str | None, Field(alias="unavailableReason")]
    metrics: Annotated[dict[str, RecipeBatchPageRowMetricsValue] | None, Field(...)]
    comparison: Annotated[str | None, Field(...)]
    annotation_name: Annotated[str | None, Field(alias="annotationName")]
    tags: list[RecipeBatchPageRowTag]
    area: Annotated[dict[str, Any] | None, Field(...)]
    scale: Annotated[RecipeBatchPageRowScale | None, Field(...)]


class RecipeBatchPageRowMetricsValue(WireModel):
    """
    Inline object hoisted from RecipeBatchPage.rows[].metrics{}.
    """

    value: float
    quantity: str
    unit: Annotated[str, Field(min_length=1)]


class RecipeBatchPageRowScale(WireModel):
    """
    Inline object hoisted from RecipeBatchPage.rows[].scale.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    units_per_pixel: Annotated[float, Field(alias="unitsPerPixel", gt=0.0)]
    unit: str


class RecipeBatchPageRowTag(WireModel):
    """
    Inline object hoisted from RecipeBatchPage.rows[].tags[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    name: Annotated[str | None, Field(...)]


class RecipeDetail(WireModel):
    """
    Wire model for OpenAPI component RecipeDetailDto.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    name: str
    description: str
    current_version: Annotated[int, Field(alias="currentVersion", gt=0, le=9007199254740991)]
    fingerprint: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    definition: RecipeDetailDefinition
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    versions: list[RecipeDetailVersion]


class RecipeDetailDefinition(WireModel):
    """
    Inline object hoisted from RecipeDetail.definition.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_: Annotated[str, Field(alias="schema")]
    slots: list[RecipeDetailDefinitionSlotPhoto | RecipeDetailDefinitionSlotAnnotations]
    steps: list[RecipeDetailDefinitionStep]


class RecipeDetailDefinitionSlotAnnotations(WireModel):
    """
    Inline object hoisted from RecipeDetail.definition.slots[].<oneOf:Annotations>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    kind: str
    of: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    select: RecipeDetailDefinitionSlotAnnotationsSelectAll | RecipeDetailDefinitionSlotAnnotationsSelectTag


class RecipeDetailDefinitionSlotAnnotationsSelectAll(WireModel):
    """
    Inline object hoisted from RecipeDetail.definition.slots[].<oneOf:Annotations>.select.<anyOf:All>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    all: Literal[True]


class RecipeDetailDefinitionSlotAnnotationsSelectTag(WireModel):
    """
    Inline object hoisted from RecipeDetail.definition.slots[].<oneOf:Annotations>.select.<anyOf:Tag>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    tag: Annotated[str, Field(max_length=80, min_length=1)]


class RecipeDetailDefinitionSlotPhoto(WireModel):
    """
    Inline object hoisted from RecipeDetail.definition.slots[].<oneOf:Photo>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    kind: str


class RecipeDetailDefinitionStep(WireModel):
    """
    Inline object hoisted from RecipeDetail.definition.steps[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    operation_key: Annotated[str, Field(alias="operationKey")]
    parameters: dict[str, Any]
    inputs: dict[str, RecipeDetailDefinitionStepInputsValue]


class RecipeDetailDefinitionStepInputsValue(WireModel):
    """
    Inline object hoisted from RecipeDetail.definition.steps[].inputs{}.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    slot: str
    series: str | None = None


class RecipeDetailVersion(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    version: Annotated[int, Field(gt=0, le=9007199254740991)]
    fingerprint: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    definition: RecipeDetailVersionDefinition
    created_by_user_id: Annotated[str, Field(alias="createdByUserId")]
    via: str
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    context: RecipeDetailVersionContextNone | RecipeDetailVersionContextPhoto | RecipeDetailVersionContextHidden
    basis: RecipeDetailVersionBasisReadable | RecipeDetailVersionBasisCountOnly


class RecipeDetailVersionBasisCountOnly(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].basis.<oneOf:CountOnly>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    access: str
    count: Annotated[int, Field(ge=0, le=9007199254740991)]


class RecipeDetailVersionBasisReadable(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].basis.<oneOf:Readable>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    access: str
    entries: list[RecipeDetailVersionBasisReadableEntry]


class RecipeDetailVersionBasisReadableEntry(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].basis.<oneOf:Readable>.entries[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    annotation_id: Annotated[str, Field(alias="annotationId")]
    revision: Annotated[int, Field(ge=0, le=9007199254740991)]
    provider_id: Annotated[str, Field(alias="providerId", min_length=1)]
    result_digest: Annotated[str, Field(alias="resultDigest", pattern="^sha256:[0-9a-f]{64}$")]
    status: str
    name: Annotated[str | None, Field(...)]
    deleted: bool


class RecipeDetailVersionContextHidden(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].context.<oneOf:Hidden>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    of: str


class RecipeDetailVersionContextNone(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].context.<oneOf:None>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str


class RecipeDetailVersionContextPhoto(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].context.<oneOf:Photo>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: str
    image_id: Annotated[str, Field(alias="imageId")]
    content_sha256: Annotated[str, Field(alias="contentSha256", pattern="^sha256:[0-9a-f]{64}$")]


class RecipeDetailVersionDefinition(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].definition.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_: Annotated[str, Field(alias="schema")]
    slots: list[RecipeDetailVersionDefinitionSlotPhoto | RecipeDetailVersionDefinitionSlotAnnotations]
    steps: list[RecipeDetailVersionDefinitionStep]


class RecipeDetailVersionDefinitionSlotAnnotations(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].definition.slots[].<oneOf:Annotations>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    kind: str
    of: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    select: (
        RecipeDetailVersionDefinitionSlotAnnotationsSelectAll | RecipeDetailVersionDefinitionSlotAnnotationsSelectTag
    )


class RecipeDetailVersionDefinitionSlotAnnotationsSelectAll(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].definition.slots[].<oneOf:Annotations>.select.<anyOf:All>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    all: Literal[True]


class RecipeDetailVersionDefinitionSlotAnnotationsSelectTag(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].definition.slots[].<oneOf:Annotations>.select.<anyOf:Tag>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    tag: Annotated[str, Field(max_length=80, min_length=1)]


class RecipeDetailVersionDefinitionSlotPhoto(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].definition.slots[].<oneOf:Photo>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    kind: str


class RecipeDetailVersionDefinitionStep(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].definition.steps[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    operation_key: Annotated[str, Field(alias="operationKey")]
    parameters: dict[str, Any]
    inputs: dict[str, RecipeDetailVersionDefinitionStepInputsValue]


class RecipeDetailVersionDefinitionStepInputsValue(WireModel):
    """
    Inline object hoisted from RecipeDetail.versions[].definition.steps[].inputs{}.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    slot: str
    series: str | None = None


class RecipeList(WireModel):
    """
    Wire model for OpenAPI component RecipeListDto.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    recipes: list[RecipeListRecipe]


class RecipeListRecipe(WireModel):
    """
    Inline object hoisted from RecipeList.recipes[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    name: str
    description: str
    current_version: Annotated[int, Field(alias="currentVersion", gt=0, le=9007199254740991)]
    fingerprint: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    definition: RecipeListRecipeDefinition
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]


class RecipeListRecipeDefinition(WireModel):
    """
    Inline object hoisted from RecipeList.recipes[].definition.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_: Annotated[str, Field(alias="schema")]
    slots: list[RecipeListRecipeDefinitionSlotPhoto | RecipeListRecipeDefinitionSlotAnnotations]
    steps: list[RecipeListRecipeDefinitionStep]


class RecipeListRecipeDefinitionSlotAnnotations(WireModel):
    """
    Inline object hoisted from RecipeList.recipes[].definition.slots[].<oneOf:Annotations>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    kind: str
    of: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    select: RecipeListRecipeDefinitionSlotAnnotationsSelectAll | RecipeListRecipeDefinitionSlotAnnotationsSelectTag


class RecipeListRecipeDefinitionSlotAnnotationsSelectAll(WireModel):
    """
    Inline object hoisted from RecipeList.recipes[].definition.slots[].<oneOf:Annotations>.select.<anyOf:All>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    all: Literal[True]


class RecipeListRecipeDefinitionSlotAnnotationsSelectTag(WireModel):
    """
    Inline object hoisted from RecipeList.recipes[].definition.slots[].<oneOf:Annotations>.select.<anyOf:Tag>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    tag: Annotated[str, Field(max_length=80, min_length=1)]


class RecipeListRecipeDefinitionSlotPhoto(WireModel):
    """
    Inline object hoisted from RecipeList.recipes[].definition.slots[].<oneOf:Photo>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    kind: str


class RecipeListRecipeDefinitionStep(WireModel):
    """
    Inline object hoisted from RecipeList.recipes[].definition.steps[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    operation_key: Annotated[str, Field(alias="operationKey")]
    parameters: dict[str, Any]
    inputs: dict[str, RecipeListRecipeDefinitionStepInputsValue]


class RecipeListRecipeDefinitionStepInputsValue(WireModel):
    """
    Inline object hoisted from RecipeList.recipes[].definition.steps[].inputs{}.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    slot: str
    series: str | None = None


class RecipeRun(WireModel):
    """
    Wire model for OpenAPI component RecipeRunViewDto.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    recipe_id: Annotated[str, Field(alias="recipeId")]
    recipe_version: Annotated[int, Field(alias="recipeVersion", gt=0, le=9007199254740991)]
    definition_fingerprint: Annotated[str, Field(alias="definitionFingerprint", pattern="^sha256:[0-9a-f]{64}$")]
    image_id: Annotated[str, Field(alias="imageId")]
    batch_id: Annotated[str | None, Field(alias="batchId")]
    rerun_of: Annotated[str | None, Field(alias="rerunOf")]
    via: str
    status: str
    failure_code: Annotated[str | None, Field(alias="failureCode")]
    comparison: Annotated[str | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    started_at: Annotated[AwareDatetime | None, Field(alias="startedAt")]
    finished_at: Annotated[AwareDatetime | None, Field(alias="finishedAt")]
    readable: bool
    binding: Annotated[dict[str, Any] | None, Field(...)]
    steps: list[RecipeRunStep]
    annotation_names: Annotated[dict[str, str], Field(alias="annotationNames")]


class RecipeRunAgain(WireModel):
    """
    Wire model for OpenAPI component RecipeRunAgainResponseDto.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    batch_id: Annotated[str | None, Field(alias="batchId")]
    runs: list[RecipeRunAgainRun]
    skipped: Annotated[int, Field(ge=0, le=9007199254740991)]


class RecipeRunAgainRun(WireModel):
    """
    Inline object hoisted from RecipeRunAgain.runs[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    image_id: Annotated[str, Field(alias="imageId")]
    status: str


class RecipeRunStart(WireModel):
    """
    Wire model for OpenAPI component RecipeRunStartResponseDto.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    batch_id: Annotated[str | None, Field(alias="batchId")]
    runs: list[RecipeRunStartRun]
    skipped: Annotated[int, Field(ge=0, le=9007199254740991)]


class RecipeRunStartRun(WireModel):
    """
    Inline object hoisted from RecipeRunStart.runs[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    image_id: Annotated[str, Field(alias="imageId")]
    status: str


class RecipeRunStep(WireModel):
    """
    Inline object hoisted from RecipeRun.steps[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    operation_key: Annotated[str, Field(alias="operationKey", pattern="^[a-z0-9][a-z0-9._-]*@[1-9][0-9]*$")]
    parameter_fingerprint: Annotated[str | None, Field(alias="parameterFingerprint", pattern="^sha256:[0-9a-f]{64}$")]
    verdict: str
    outputs: list[RecipeRunStepOutput]


class RecipeRunStepOutput(WireModel):
    """
    Inline object hoisted from RecipeRun.steps[].outputs[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    annotation_id: Annotated[str, Field(alias="annotationId")]
    provider_id: Annotated[str, Field(alias="providerId", min_length=1)]
    operation_key: Annotated[str, Field(alias="operationKey", pattern="^[a-z0-9][a-z0-9._-]*@[1-9][0-9]*$")]
    result_digest: Annotated[str, Field(alias="resultDigest", pattern="^sha256:[0-9a-f]{64}$")]
    status: str
    unavailable_reason: Annotated[str | None, Field(alias="unavailableReason")]
    metrics: dict[str, RecipeRunStepOutputMetricsValue]
    provenance: Annotated[RecipeRunStepOutputProvenance | None, Field(...)]
    comparison: str | None = None


class RecipeRunStepOutputMetricsValue(WireModel):
    """
    Inline object hoisted from RecipeRun.steps[].outputs[].metrics{}.
    """

    value: float
    quantity: str
    unit: Annotated[str, Field(min_length=1)]


class RecipeRunStepOutputProvenance(WireModel):
    """
    Inline object hoisted from RecipeRun.steps[].outputs[].provenance.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    image_lib: Annotated[str, Field(alias="imageLib", min_length=1)]
    host: str
    codec: RecipeRunStepOutputProvenanceCodec | None = None


class RecipeRunStepOutputProvenanceCodec(WireModel):
    """
    Inline object hoisted from RecipeRun.steps[].outputs[].provenance.codec.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]


class RecipeSummary(WireModel):
    """
    Wire model for OpenAPI component RecipeSummaryDto.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    name: str
    description: str
    current_version: Annotated[int, Field(alias="currentVersion", gt=0, le=9007199254740991)]
    fingerprint: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    definition: RecipeSummaryDefinition
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]


class RecipeSummaryDefinition(WireModel):
    """
    Inline object hoisted from RecipeSummary.definition.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_: Annotated[str, Field(alias="schema")]
    slots: list[RecipeSummaryDefinitionSlotPhoto | RecipeSummaryDefinitionSlotAnnotations]
    steps: list[RecipeSummaryDefinitionStep]


class RecipeSummaryDefinitionSlotAnnotations(WireModel):
    """
    Inline object hoisted from RecipeSummary.definition.slots[].<oneOf:Annotations>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    kind: str
    of: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    select: RecipeSummaryDefinitionSlotAnnotationsSelectAll | RecipeSummaryDefinitionSlotAnnotationsSelectTag


class RecipeSummaryDefinitionSlotAnnotationsSelectAll(WireModel):
    """
    Inline object hoisted from RecipeSummary.definition.slots[].<oneOf:Annotations>.select.<anyOf:All>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    all: Literal[True]


class RecipeSummaryDefinitionSlotAnnotationsSelectTag(WireModel):
    """
    Inline object hoisted from RecipeSummary.definition.slots[].<oneOf:Annotations>.select.<anyOf:Tag>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    tag: Annotated[str, Field(max_length=80, min_length=1)]


class RecipeSummaryDefinitionSlotPhoto(WireModel):
    """
    Inline object hoisted from RecipeSummary.definition.slots[].<oneOf:Photo>.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(pattern="^[a-z][a-z0-9-]{0,31}$")]
    kind: str


class RecipeSummaryDefinitionStep(WireModel):
    """
    Inline object hoisted from RecipeSummary.definition.steps[].
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: str
    operation_key: Annotated[str, Field(alias="operationKey")]
    parameters: dict[str, Any]
    inputs: dict[str, RecipeSummaryDefinitionStepInputsValue]


class RecipeSummaryDefinitionStepInputsValue(WireModel):
    """
    Inline object hoisted from RecipeSummary.definition.steps[].inputs{}.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    slot: str
    series: str | None = None


class Rule(WireModel):
    """
    Wire model for OpenAPI component RuleResponseDto.
    """

    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str | None, Field(...)]
    trigger_type: Annotated[str, Field(alias="triggerType")]
    trigger_config: Annotated[
        RuleTriggerConfigCron | RuleTriggerConfigEvent | RuleTriggerConfigCondition | dict[str, Any],
        Field(alias="triggerConfig"),
    ]
    conditions: dict[str, Any]
    actions: list[RuleAction]
    enabled: bool
    priority: Annotated[int, Field(ge=0, le=9007199254740991)]
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    spot_id: Annotated[str, Field(alias="spotId", min_length=1)]
    device_id: Annotated[str | None, Field(alias="deviceId", min_length=1)]


class RuleAction(WireModel):
    """
    Inline object hoisted from Rule.actions[].
    """

    action_def_id: Annotated[
        str,
        Field(
            alias="actionDefId",
            description="Reference to ActionDefinition",
            min_length=1,
        ),
    ]
    component_id: Annotated[
        str,
        Field(
            alias="componentId",
            description="Component ID (Camera Plan integration)",
            min_length=1,
        ),
    ]
    params: Annotated[dict[str, Any] | None, Field(description="Execution parameters")] = None
    capture_session_options: Annotated[RuleActionCaptureSessionOptions | None, Field(alias="captureSessionOptions")] = (
        None
    )
    order: Annotated[
        int,
        Field(
            description="Execution order (lower executes first)",
            ge=0,
            le=9007199254740991,
        ),
    ] = 0
    control_type: Annotated[
        str | None,
        Field(
            alias="controlType",
            description="Control type classification (populated from ActionDefinition)",
        ),
    ] = None
    action_definition: Annotated[RuleActionActionDefinition | None, Field(alias="actionDefinition")] = None


class RuleActionActionDefinition(WireModel):
    """
    ActionDefinition details for display (API populated)
    """

    id: str
    name: str
    name_translation: Annotated[RuleActionActionDefinitionNameTranslation | None, Field(alias="nameTranslation")]
    action_type: Annotated[str, Field(alias="actionType")]


class RuleActionActionDefinitionNameTranslation(WireModel):
    """
    Inline object hoisted from Rule.actions[].actionDefinition.nameTranslation.
    """

    ko: str | None = None
    en: str | None = None


class RuleActionCaptureSessionOptions(WireModel):
    """
    CaptureSession metadata applied when this action creates a capture session
    """

    tag_ids: Annotated[list[str] | None, Field(alias="tagIds", max_length=100)] = None


class RuleExecution(WireModel):
    """
    Wire model for OpenAPI component RuleExecutionResponseDto.
    """

    id: Annotated[str, Field(min_length=1)]
    rule_id: Annotated[str, Field(alias="ruleId", min_length=1)]
    status: str
    actual_start_time: Annotated[AwareDatetime, Field(alias="actualStartTime")]
    actual_end_time: Annotated[AwareDatetime | None, Field(alias="actualEndTime")]
    duration: Annotated[int | None, Field(ge=0, le=9007199254740991)]
    actions_executed: Annotated[list[RuleExecutionActionsExecuted] | None, Field(alias="actionsExecuted")]
    error_message: Annotated[str | None, Field(alias="errorMessage")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    rule: RuleExecutionRule | None = None


class RuleExecutionActionsExecuted(WireModel):
    """
    Inline object hoisted from RuleExecution.actionsExecuted[].
    """

    action_def_id: Annotated[str, Field(alias="actionDefId")]
    execution_id: Annotated[str, Field(alias="executionId")]
    status: str
    duration: Annotated[float | None, Field(...)]


class RuleExecutionRule(WireModel):
    """
    Inline object hoisted from RuleExecution.rule.
    """

    id: str
    name: str
    spot_id: Annotated[str, Field(alias="spotId")]


class RuleTriggerConfigCondition(WireModel):
    """
    Inline object hoisted from Rule.triggerConfig.<anyOf:Condition>.
    """

    expression: Annotated[str, Field(description="Condition expression (e.g., CEL)", min_length=1)]
    check_interval: Annotated[
        int | None,
        Field(
            alias="checkInterval",
            description="Check interval in milliseconds",
            ge=1000,
            le=9007199254740991,
        ),
    ] = None


class RuleTriggerConfigCron(WireModel):
    """
    Inline object hoisted from Rule.triggerConfig.<anyOf:Cron>.
    """

    cron_expression: Annotated[
        str,
        Field(
            alias="cronExpression",
            description='Cron expression (e.g., "0 9 * * *")',
            min_length=1,
        ),
    ]


class RuleTriggerConfigEvent(WireModel):
    """
    Inline object hoisted from Rule.triggerConfig.<anyOf:Event>.
    """

    event_type: Annotated[str, Field(alias="eventType", description="Event type identifier", min_length=1)]
    filters: Annotated[dict[str, Any] | None, Field(description="Event filters")] = None


class Spot(WireModel):
    """
    Wire model for OpenAPI component SpotWithHierarchyResponseDto.
    """

    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    slug: Annotated[str, Field(min_length=1)]
    description: Annotated[str | None, Field(...)]
    location: Annotated[str | None, Field(...)]
    is_active: Annotated[bool, Field(alias="isActive")] = True
    organization_id: Annotated[str, Field(alias="organizationId", min_length=1)]
    product_id: Annotated[str | None, Field(alias="productId")]
    group_id: Annotated[str | None, Field(alias="groupId")]
    full_path: Annotated[str | None, Field(alias="fullPath")] = None
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    group: Annotated[SpotGroup | None, Field(...)]
    tags: Annotated[list[SpotTag], Field(validate_default=True)] = []
    device_stats: Annotated[SpotDeviceStats | None, Field(alias="deviceStats")] = None
    agents: Annotated[list[SpotAgent], Field(validate_default=True)] = []
    agents_summary: Annotated[SpotAgentsSummary | None, Field(alias="agentsSummary")] = None
    storage_used: Annotated[str | None, Field(alias="storageUsed")] = None
    storage_file_count: Annotated[int | None, Field(alias="storageFileCount", ge=0, le=9007199254740991)] = None


class SpotAgent(WireModel):
    """
    Inline object hoisted from Spot.agents[].
    """

    id: str
    name: str
    identifier: str
    type: str
    status: str
    created_at: Annotated[AwareDatetime | None, Field(alias="createdAt")] = None
    updated_at: Annotated[AwareDatetime | None, Field(alias="updatedAt")] = None
    device: Annotated[SpotAgentDevice | None, Field(...)]
    realtime_status: Annotated[SpotAgentRealtimeStatus | None, Field(alias="realtimeStatus")]
    recent_error_count: Annotated[int, Field(alias="recentErrorCount", ge=0, le=9007199254740991)]


class SpotAgentDevice(WireModel):
    """
    Inline object hoisted from Spot.agents[].device.
    """

    id: str
    name: str
    identifier: str
    type: str


class SpotAgentRealtimeStatus(WireModel):
    """
    Inline object hoisted from Spot.agents[].realtimeStatus.
    """

    is_online: Annotated[bool, Field(alias="isOnline")]
    last_seen: Annotated[AwareDatetime | None, Field(alias="lastSeen")]
    status: str
    health: Annotated[SpotAgentRealtimeStatusHealth | None, Field(...)]
    accepts_commands: Annotated[bool | None, Field(alias="acceptsCommands")] = None


class SpotAgentRealtimeStatusHealth(WireModel):
    """
    Inline object hoisted from Spot.agents[].realtimeStatus.health.
    """

    cpu: Annotated[float, Field(ge=0.0, le=100.0)]
    memory: Annotated[float, Field(ge=0.0, le=100.0)]
    disk: Annotated[float, Field(ge=0.0, le=100.0)]


class SpotAgentsSummary(WireModel):
    """
    Inline object hoisted from Spot.agentsSummary.
    """

    total: Annotated[int, Field(ge=0, le=9007199254740991)]
    online: Annotated[int, Field(ge=0, le=9007199254740991)]
    offline: Annotated[int, Field(ge=0, le=9007199254740991)]
    avg_health: Annotated[SpotAgentsSummaryAvgHealth, Field(alias="avgHealth")]


class SpotAgentsSummaryAvgHealth(WireModel):
    """
    Inline object hoisted from Spot.agentsSummary.avgHealth.
    """

    cpu: Annotated[float, Field(ge=0.0, le=100.0)]
    memory: Annotated[float, Field(ge=0.0, le=100.0)]
    disk: Annotated[float, Field(ge=0.0, le=100.0)]


class SpotDeviceStats(WireModel):
    """
    Inline object hoisted from Spot.deviceStats.
    """

    total: Annotated[int, Field(ge=0, le=9007199254740991)]
    online: Annotated[int, Field(ge=0, le=9007199254740991)]
    offline: Annotated[int, Field(ge=0, le=9007199254740991)]
    error: Annotated[int, Field(ge=0, le=9007199254740991)]
    maintenance: Annotated[int, Field(ge=0, le=9007199254740991)]
    average_health_score: Annotated[float, Field(alias="averageHealthScore", ge=0.0, le=100.0)]


class SpotGroup(WireModel):
    """
    Wire model for OpenAPI component SpotWithHierarchyResponseDto__schema0.
    """

    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str | None, Field(...)]
    slug: Annotated[str, Field(min_length=1)]
    parent_id: Annotated[str | None, Field(alias="parentId")]
    path: Annotated[str | None, Field(...)]
    organization_id: Annotated[str, Field(alias="organizationId", min_length=1)]
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    spot_count: Annotated[int, Field(alias="spotCount", ge=0, le=9007199254740991)]
    child_count: Annotated[int, Field(alias="childCount", ge=0, le=9007199254740991)]
    depth: Annotated[int, Field(ge=0, le=9007199254740991)]
    children: Annotated[list[SpotGroup], Field(validate_default=True)] = []
    parent: SpotGroupParent | None = None


class SpotGroupParent(WireModel):
    """
    Inline object hoisted from SpotGroup.parent.
    """

    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str | None, Field(...)]
    slug: Annotated[str, Field(min_length=1)]
    parent_id: Annotated[str | None, Field(alias="parentId")]
    path: Annotated[str | None, Field(...)]
    organization_id: Annotated[str, Field(alias="organizationId", min_length=1)]
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]


class SpotStructure(WireModel):
    """
    Wire model for OpenAPI component SpotStructureResponseDto.
    """

    spot: SpotStructureSpot
    devices: list[SpotStructureDevice]
    rules: list[SpotStructureRule]
    stats: SpotStructureStats


class SpotStructureDevice(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].
    """

    id: str
    identifier: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    type: Annotated[str, Field(min_length=1)]
    model: Annotated[str | None, Field(...)]
    serial_number: Annotated[str | None, Field(alias="serialNumber")]
    hardware_hash: Annotated[str | None, Field(alias="hardwareHash")]
    configuration: Annotated[dict[str, Any] | None, Field(...)]
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    agent_id: Annotated[str | None, Field(alias="agentId")]
    spot_id: Annotated[str, Field(alias="spotId")]
    components: list[SpotStructureDeviceComponent]
    topics: list[SpotStructureDeviceTopic]
    actions: list[SpotStructureDeviceAction]


class SpotStructureDeviceAction(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].actions[].
    """

    id: str
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str | None, Field(...)]
    action_type: Annotated[str, Field(alias="actionType")]
    handler_type: Annotated[str, Field(alias="handlerType", min_length=1)]
    parameters: Annotated[dict[str, Any] | None, Field(...)]
    name_translation: Annotated[SpotStructureDeviceActionNameTranslation | None, Field(alias="nameTranslation")]
    timeout: Annotated[int, Field(ge=1, le=86400)] = 30
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[SpotStructureDeviceActionMetadata | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    device_id: Annotated[str | None, Field(alias="deviceId")]
    component_id: Annotated[str | None, Field(alias="componentId")]


class SpotStructureDeviceActionMetadata(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].actions[].metadata.
    """

    ui: SpotStructureDeviceActionMetadataUi | None = None


class SpotStructureDeviceActionMetadataUi(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].actions[].metadata.ui.
    """

    category: str
    order: Annotated[int | None, Field(ge=0, le=9007199254740991)] = None
    display_context: Annotated[list[str] | None, Field(alias="displayContext")] = None
    control_type: Annotated[str | None, Field(alias="controlType")] = None


class SpotStructureDeviceActionNameTranslation(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].actions[].nameTranslation.
    """

    ko: str | None = None
    en: str | None = None


class SpotStructureDeviceComponent(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].components[].
    """

    id: str
    identifier: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    component_type: Annotated[str, Field(alias="componentType", min_length=1)]
    category: str
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    device_id: Annotated[str, Field(alias="deviceId")]
    topics: list[SpotStructureDeviceComponentTopic]
    actions: list[SpotStructureDeviceComponentAction]


class SpotStructureDeviceComponentAction(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].components[].actions[].
    """

    id: str
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str | None, Field(...)]
    action_type: Annotated[str, Field(alias="actionType")]
    handler_type: Annotated[str, Field(alias="handlerType", min_length=1)]
    parameters: Annotated[dict[str, Any] | None, Field(...)]
    name_translation: Annotated[
        SpotStructureDeviceComponentActionNameTranslation | None,
        Field(alias="nameTranslation"),
    ]
    timeout: Annotated[int, Field(ge=1, le=86400)] = 30
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[SpotStructureDeviceComponentActionMetadata | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    device_id: Annotated[str | None, Field(alias="deviceId")]
    component_id: Annotated[str | None, Field(alias="componentId")]


class SpotStructureDeviceComponentActionMetadata(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].components[].actions[].metadata.
    """

    ui: SpotStructureDeviceComponentActionMetadataUi | None = None


class SpotStructureDeviceComponentActionMetadataUi(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].components[].actions[].metadata.ui.
    """

    category: str
    order: Annotated[int | None, Field(ge=0, le=9007199254740991)] = None
    display_context: Annotated[list[str] | None, Field(alias="displayContext")] = None
    control_type: Annotated[str | None, Field(alias="controlType")] = None


class SpotStructureDeviceComponentActionNameTranslation(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].components[].actions[].nameTranslation.
    """

    ko: str | None = None
    en: str | None = None


class SpotStructureDeviceComponentTopic(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].components[].topics[].
    """

    id: str
    name: Annotated[str, Field(min_length=1)]
    path: Annotated[str, Field(min_length=1)]
    data_type: Annotated[str, Field(alias="dataType")]
    unit: Annotated[str | None, Field(...)]
    type: str
    qos: Annotated[int, Field(ge=0, le=2)] = 0
    retained: bool = False
    metadata: SpotStructureDeviceComponentTopicMetadata | None = None
    metric_name: Annotated[str | None, Field(alias="metricName")]
    metric_labels: Annotated[dict[str, Any] | None, Field(alias="metricLabels")]
    sampling_rate: Annotated[int | None, Field(alias="samplingRate", ge=0, le=9007199254740991)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    device_id: Annotated[str | None, Field(alias="deviceId")]
    component_id: Annotated[str | None, Field(alias="componentId")]


class SpotStructureDeviceComponentTopicMetadata(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].components[].topics[].metadata.
    """

    telemetry_category: Annotated[str | None, Field(alias="telemetryCategory")] = None
    description: str | None = None
    label: Annotated[str | None, Field(max_length=100, min_length=1)] = None
    unit: str | None = None
    value_type: Annotated[str | None, Field(alias="valueType")] = None
    domain: Annotated[list[float] | None, Field(max_length=2, min_length=2)] = None
    state_mapping: Annotated[
        dict[str, SpotStructureDeviceComponentTopicMetadataStateMappingValue] | None,
        Field(alias="stateMapping"),
    ] = None
    disabled_by: Annotated[str | None, Field(alias="disabledBy")] = None
    source: str | None = None
    dimensionality: Annotated[int | None, Field(gt=0, le=9007199254740991)] = None


class SpotStructureDeviceComponentTopicMetadataStateMappingValue(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].components[].topics[].metadata.stateMapping{}.
    """

    label: str


class SpotStructureDeviceTopic(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].topics[].
    """

    id: str
    name: Annotated[str, Field(min_length=1)]
    path: Annotated[str, Field(min_length=1)]
    data_type: Annotated[str, Field(alias="dataType")]
    unit: Annotated[str | None, Field(...)]
    type: str
    qos: Annotated[int, Field(ge=0, le=2)] = 0
    retained: bool = False
    metadata: SpotStructureDeviceTopicMetadata | None = None
    metric_name: Annotated[str | None, Field(alias="metricName")]
    metric_labels: Annotated[dict[str, Any] | None, Field(alias="metricLabels")]
    sampling_rate: Annotated[int | None, Field(alias="samplingRate", ge=0, le=9007199254740991)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    device_id: Annotated[str | None, Field(alias="deviceId")]
    component_id: Annotated[str | None, Field(alias="componentId")]


class SpotStructureDeviceTopicMetadata(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].topics[].metadata.
    """

    telemetry_category: Annotated[str | None, Field(alias="telemetryCategory")] = None
    description: str | None = None
    label: Annotated[str | None, Field(max_length=100, min_length=1)] = None
    unit: str | None = None
    value_type: Annotated[str | None, Field(alias="valueType")] = None
    domain: Annotated[list[float] | None, Field(max_length=2, min_length=2)] = None
    state_mapping: Annotated[
        dict[str, SpotStructureDeviceTopicMetadataStateMappingValue] | None,
        Field(alias="stateMapping"),
    ] = None
    disabled_by: Annotated[str | None, Field(alias="disabledBy")] = None
    source: str | None = None
    dimensionality: Annotated[int | None, Field(gt=0, le=9007199254740991)] = None


class SpotStructureDeviceTopicMetadataStateMappingValue(WireModel):
    """
    Inline object hoisted from SpotStructure.devices[].topics[].metadata.stateMapping{}.
    """

    label: str


class SpotStructureRule(WireModel):
    """
    Inline object hoisted from SpotStructure.rules[].
    """

    id: str
    name: Annotated[str, Field(min_length=1)]
    description: Annotated[str | None, Field(...)]
    trigger_type: Annotated[str, Field(alias="triggerType")]
    trigger_config: Annotated[
        SpotStructureRuleTriggerConfigCron
        | SpotStructureRuleTriggerConfigEvent
        | SpotStructureRuleTriggerConfigCondition
        | dict[str, Any],
        Field(alias="triggerConfig"),
    ]
    conditions: dict[str, Any]
    actions: Annotated[list[SpotStructureRuleAction], Field(validate_default=True)] = []
    enabled: bool = True
    priority: Annotated[int, Field(ge=0, le=9007199254740991)] = 0
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]
    spot_id: Annotated[str, Field(alias="spotId")]
    device_id: Annotated[str | None, Field(alias="deviceId")]


class SpotStructureRuleAction(WireModel):
    """
    Inline object hoisted from SpotStructure.rules[].actions[].
    """

    action_def_id: Annotated[
        str,
        Field(
            alias="actionDefId",
            description="Reference to ActionDefinition",
            min_length=1,
        ),
    ]
    component_id: Annotated[
        str,
        Field(
            alias="componentId",
            description="Component ID (Camera Plan integration)",
            min_length=1,
        ),
    ]
    params: Annotated[dict[str, Any] | None, Field(description="Execution parameters")] = None
    capture_session_options: Annotated[
        SpotStructureRuleActionCaptureSessionOptions | None,
        Field(alias="captureSessionOptions"),
    ] = None
    order: Annotated[
        int,
        Field(
            description="Execution order (lower executes first)",
            ge=0,
            le=9007199254740991,
        ),
    ] = 0
    control_type: Annotated[
        str | None,
        Field(
            alias="controlType",
            description="Control type classification (populated from ActionDefinition)",
        ),
    ] = None
    action_definition: Annotated[SpotStructureRuleActionActionDefinition | None, Field(alias="actionDefinition")] = None


class SpotStructureRuleActionActionDefinition(WireModel):
    """
    ActionDefinition details for display (API populated)
    """

    id: str
    name: str
    name_translation: Annotated[
        SpotStructureRuleActionActionDefinitionNameTranslation | None,
        Field(alias="nameTranslation"),
    ]
    action_type: Annotated[str, Field(alias="actionType")]


class SpotStructureRuleActionActionDefinitionNameTranslation(WireModel):
    """
    Inline object hoisted from SpotStructure.rules[].actions[].actionDefinition.nameTranslation.
    """

    ko: str | None = None
    en: str | None = None


class SpotStructureRuleActionCaptureSessionOptions(WireModel):
    """
    CaptureSession metadata applied when this action creates a capture session
    """

    tag_ids: Annotated[list[str] | None, Field(alias="tagIds", max_length=100)] = None


class SpotStructureRuleTriggerConfigCondition(WireModel):
    """
    Inline object hoisted from SpotStructure.rules[].triggerConfig.<anyOf:Condition>.
    """

    expression: Annotated[str, Field(description="Condition expression (e.g., CEL)", min_length=1)]
    check_interval: Annotated[
        int | None,
        Field(
            alias="checkInterval",
            description="Check interval in milliseconds",
            ge=1000,
            le=9007199254740991,
        ),
    ] = None


class SpotStructureRuleTriggerConfigCron(WireModel):
    """
    Inline object hoisted from SpotStructure.rules[].triggerConfig.<anyOf:Cron>.
    """

    cron_expression: Annotated[
        str,
        Field(
            alias="cronExpression",
            description='Cron expression (e.g., "0 9 * * *")',
            min_length=1,
        ),
    ]


class SpotStructureRuleTriggerConfigEvent(WireModel):
    """
    Inline object hoisted from SpotStructure.rules[].triggerConfig.<anyOf:Event>.
    """

    event_type: Annotated[str, Field(alias="eventType", description="Event type identifier", min_length=1)]
    filters: Annotated[dict[str, Any] | None, Field(description="Event filters")] = None


class SpotStructureSpot(WireModel):
    """
    Inline object hoisted from SpotStructure.spot.
    """

    id: str
    name: Annotated[str, Field(min_length=1)]
    slug: Annotated[str, Field(min_length=1)]
    description: Annotated[str | None, Field(...)]
    location: Annotated[str | None, Field(...)]
    is_active: Annotated[bool, Field(alias="isActive")] = True
    organization_id: Annotated[str, Field(alias="organizationId")]
    product_id: Annotated[str | None, Field(alias="productId")]
    group_id: Annotated[str | None, Field(alias="groupId")]
    full_path: Annotated[str | None, Field(alias="fullPath")] = None
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]


class SpotStructureStats(WireModel):
    """
    Inline object hoisted from SpotStructure.stats.
    """

    device_count: Annotated[int, Field(alias="deviceCount", ge=0, le=9007199254740991)]
    component_count: Annotated[int, Field(alias="componentCount", ge=0, le=9007199254740991)]
    topic_count: Annotated[int, Field(alias="topicCount", ge=0, le=9007199254740991)]
    rule_count: Annotated[int, Field(alias="ruleCount", ge=0, le=9007199254740991)]
    action_count: Annotated[int, Field(alias="actionCount", ge=0, le=9007199254740991)]


class SpotTag(WireModel):
    """
    Inline object hoisted from Spot.tags[].
    """

    id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    slug: Annotated[str, Field(min_length=1)]
    color: Annotated[str | None, Field(...)]
    icon: Annotated[str | None, Field(...)]
    description: Annotated[str | None, Field(...)]
    is_system: Annotated[bool, Field(alias="isSystem")] = False
    organization_id: Annotated[str, Field(alias="organizationId", min_length=1)]
    usage_count: Annotated[int, Field(alias="usageCount", ge=0, le=9007199254740991)] = 0
    deleted_at: Annotated[AwareDatetime | None, Field(alias="deletedAt")]
    metadata: Annotated[dict[str, Any] | None, Field(...)]
    created_at: Annotated[AwareDatetime, Field(alias="createdAt")]
    updated_at: Annotated[AwareDatetime, Field(alias="updatedAt")]


class Telemetry(WireModel):
    """
    Untyped in the committed OpenAPI artifact: ManagementTelemetryController_getTelemetry declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class TelemetryBatch(WireModel):
    """
    Untyped in the committed OpenAPI artifact: ManagementTelemetryController_getTelemetryBatch declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class TelemetryBatchExport(WireModel):
    """
    Untyped in the committed OpenAPI artifact: ManagementTelemetryController_getTelemetryBatchExport declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class TelemetryBatchRollup(WireModel):
    """
    Untyped in the committed OpenAPI artifact: ManagementTelemetryController_getTelemetryBatchRollup declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class TelemetryTopics(WireModel):
    """
    Untyped in the committed OpenAPI artifact: ManagementTelemetryController_getTopics declares no response schema, so every field is exposed as an extra (model_extra / item access).
    """

    model_config = ConfigDict(
        extra="allow",
    )


class UploadImageResponse(WireModel):
    """
    Wire model for OpenAPI component UploadImageResponseDto.
    """

    upload_url: Annotated[str, Field(alias="uploadUrl")]
    thumbnail_upload_url: Annotated[str, Field(alias="thumbnailUploadUrl")]
    media_asset_id: Annotated[str, Field(alias="mediaAssetId", min_length=1)]
    file_id: Annotated[str, Field(alias="fileId")]
    thumbnail_file_id: Annotated[str, Field(alias="thumbnailFileId")]
    expires_in: Annotated[int, Field(alias="expiresIn", gt=0, le=9007199254740991)]
    file_key: Annotated[str | None, Field(alias="fileKey")] = None
    thumbnail_file_key: Annotated[str | None, Field(alias="thumbnailFileKey")] = None
    expires_at: Annotated[AwareDatetime | None, Field(alias="expiresAt")] = None


class ZarrFiles(WireModel):
    """
    Wire model for OpenAPI component ZarrFilesResponseDto.
    """

    media_asset_id: Annotated[str, Field(alias="mediaAssetId")]
    zarr_root_key: Annotated[str, Field(alias="zarrRootKey", min_length=1)]
    files: dict[str, str]
    total_files: Annotated[int, Field(alias="totalFiles", ge=0, le=9007199254740991)]
    expires_in: Annotated[int, Field(alias="expiresIn", gt=0, le=9007199254740991)]
    member_sizes: Annotated[dict[str, MemberSizesAdditionalProperty] | None, Field(alias="memberSizes")] = None
    total_bytes: Annotated[int | None, Field(alias="totalBytes", ge=0, le=9007199254740991)] = None
    download_ready: Annotated[bool | None, Field(alias="downloadReady")] = None
    completed_bytes: Annotated[int | None, Field(alias="completedBytes", ge=0, le=9007199254740991)] = None


SpotGroup.model_rebuild()


G3_OPERATION_ALLOWLIST = frozenset(
    {
        ("DELETE", "/api/v1/agents/management/{id}/access-keys/{keyId}"),
        ("DELETE", "/api/v1/tool-gateway/sessions/{sessionId}"),
        ("GET", "/api/v1/actions/executions"),
        ("GET", "/api/v1/actions/executions/batch"),
        ("GET", "/api/v1/actions/executions/{id}"),
        ("GET", "/api/v1/agents/management"),
        ("GET", "/api/v1/agents/management/{id}/access-keys"),
        ("GET", "/api/v1/agents/management/{id}/access-keys/{keyId}/plain-key"),
        ("GET", "/api/v1/agents/management/{id}/telemetry"),
        ("GET", "/api/v1/agents/management/{id}/telemetry/batch"),
        ("GET", "/api/v1/agents/management/{id}/telemetry/batch-export"),
        ("GET", "/api/v1/agents/management/{id}/telemetry/batch-rollup"),
        ("GET", "/api/v1/agents/management/{id}/topics"),
        ("GET", "/api/v1/agents/media/assets/{id}/band-provenance"),
        ("GET", "/api/v1/analysis/recipe-batches/{batchId}"),
        ("GET", "/api/v1/analysis/recipe-runs/{runId}"),
        ("GET", "/api/v1/analysis/recipes"),
        ("GET", "/api/v1/analysis/recipes/{id}"),
        ("GET", "/api/v1/auth/access/me"),
        ("GET", "/api/v1/components"),
        ("GET", "/api/v1/devices"),
        ("GET", "/api/v1/devices/{id}"),
        ("GET", "/api/v1/devices/{id}/status"),
        ("GET", "/api/v1/media/assets"),
        ("GET", "/api/v1/media/assets/spots/{spotId}/latest"),
        ("GET", "/api/v1/media/assets/{id}"),
        ("GET", "/api/v1/media/assets/{id}/band-provenance"),
        ("GET", "/api/v1/media/assets/{id}/presigned-url"),
        ("GET", "/api/v1/media/assets/{id}/zarr-files"),
        ("GET", "/api/v1/media/capture-sessions"),
        ("GET", "/api/v1/media/capture-sessions/{id}"),
        ("GET", "/api/v1/organizations"),
        ("GET", "/api/v1/organizations/slug/{slug}"),
        ("GET", "/api/v1/organizations/user/{userId}"),
        ("GET", "/api/v1/organizations/{id}"),
        ("GET", "/api/v1/spots"),
        ("GET", "/api/v1/spots/by-slug/{slug}"),
        ("GET", "/api/v1/spots/{id}"),
        ("GET", "/api/v1/spots/{id}/structure"),
        ("GET", "/api/v1/spots/{spotId}/rules"),
        ("GET", "/api/v1/spots/{spotId}/rules/{id}"),
        ("GET", "/api/v1/spots/{spotId}/rules/{id}/executions"),
        ("GET", "/api/v1/tool-gateway/sessions/{sessionId}"),
        ("PATCH", "/api/v1/analysis/recipes/{id}"),
        ("POST", "/api/v1/actions/executions/manual"),
        ("POST", "/api/v1/actions/executions/preview"),
        ("POST", "/api/v1/agents/device/action-executions"),
        ("POST", "/api/v1/agents/device/components/capabilities"),
        ("POST", "/api/v1/agents/device/heartbeat"),
        ("POST", "/api/v1/agents/device/self-discovery"),
        ("POST", "/api/v1/agents/device/self-register"),
        ("POST", "/api/v1/agents/device/shutdown-notify"),
        ("POST", "/api/v1/agents/device/telemetry/batch"),
        ("POST", "/api/v1/agents/management"),
        ("POST", "/api/v1/agents/management/{id}/access-keys"),
        ("POST", "/api/v1/agents/management/{id}/access-keys/{keyId}/reissue"),
        ("POST", "/api/v1/agents/management/{id}/access-keys/{keyId}/rotate"),
        ("POST", "/api/v1/agents/management/{id}/telemetry/export"),
        ("POST", "/api/v1/agents/media/assets/complete-image-upload"),
        ("POST", "/api/v1/agents/media/assets/upload-image"),
        ("POST", "/api/v1/agents/media/assets/zarr/complete"),
        ("POST", "/api/v1/agents/media/assets/zarr/upload"),
        ("POST", "/api/v1/agents/media/capture-sessions"),
        ("POST", "/api/v1/agents/media/capture-sessions/{id}/cancel"),
        ("POST", "/api/v1/agents/media/capture-sessions/{id}/complete"),
        ("POST", "/api/v1/agents/media/capture-sessions/{id}/fail"),
        ("POST", "/api/v1/agents/media/capture-sessions/{id}/start"),
        ("POST", "/api/v1/analysis/recipe-batches/{batchId}/cancel"),
        ("POST", "/api/v1/analysis/recipe-batches/{batchId}/recheck"),
        ("POST", "/api/v1/analysis/recipe-batches/{batchId}/retry"),
        ("POST", "/api/v1/analysis/recipe-runs/{runId}/recheck"),
        ("POST", "/api/v1/analysis/recipes"),
        ("POST", "/api/v1/analysis/recipes/{id}/runs"),
        ("POST", "/api/v1/artifacts/{artifactId}/open"),
        ("POST", "/api/v1/media/assets/complete-image-upload"),
        ("POST", "/api/v1/media/assets/upload-image"),
        ("POST", "/api/v1/media/assets/zarr/complete"),
        ("POST", "/api/v1/media/assets/zarr/upload"),
        ("POST", "/api/v1/spots"),
        ("POST", "/api/v1/tool-gateway/sessions"),
    }
)

__all__ = [
    "AccessInfo",
    "AccessInfoCurrentOrganization",
    "AccessInfoUser",
    "AccessKey",
    "ActionExecutionBatchStatus",
    "ActionExecutionBatchStatusExecutionsValue",
    "ActionExecutionSearchResult",
    "ActionExecutionSearchResultItem",
    "ActionExecutionSearchResultPagination",
    "ActionExecutionStatus",
    "ActionExecutionStatusError",
    "ActionExecutionStatusResultCache",
    "ActionExecutionStatusResultDb",
    "Agent",
    "AgentCaptureSession",
    "AgentImageUpload",
    "AgentImageUploadComplete",
    "ArtifactDownload",
    "BandProvenance",
    "BandProvenanceBandInterpretation",
    "BandProvenanceBandInterpretationBandApprovedProfile",
    "BandProvenanceBandInterpretationBandApprovedProfileBasis",
    "BandProvenanceBandInterpretationBandUnresolved",
    "BandProvenanceBandInterpretationBandUserConfirmed",
    "BandProvenanceBandInterpretationBandVerifiedMetadata",
    "BandProvenanceBandInterpretationBandVerifiedMetadataBasis",
    "BandProvenanceBandRegistrationRegisteredCameraMetadata",
    "BandProvenanceBandRegistrationRegisteredCameraMetadataAligner",
    "BandProvenanceBandRegistrationRegisteredCameraMetadataGrid",
    "BandProvenanceBandRegistrationRegisteredCameraMetadataRecordedBy",
    "BandProvenanceBandRegistrationRegisteredCameraMetadataTransform",
    "BandProvenanceBandRegistrationRegisteredManualProfile",
    "BandProvenanceBandRegistrationRegisteredManualProfileAligner",
    "BandProvenanceBandRegistrationRegisteredManualProfileGrid",
    "BandProvenanceBandRegistrationRegisteredManualProfileProfile",
    "BandProvenanceBandRegistrationRegisteredManualProfileRecordedBy",
    "BandProvenanceBandRegistrationRegisteredManualProfileTransform",
    "BandProvenanceBandRegistrationRegisteredProcessedProduct",
    "BandProvenanceBandRegistrationRegisteredProcessedProductGrid",
    "BandProvenanceBandRegistrationRegisteredProcessedProductRecordedBy",
    "BandProvenanceBandRegistrationUnknown",
    "BandProvenanceBandRegistrationUnknownRecordedBy",
    "BandProvenanceBandRegistrationUnregistered",
    "BandProvenanceBandRegistrationUnregisteredRecordedBy",
    "BandProvenanceNormalization",
    "BandProvenanceNormalizationRecord",
    "BandProvenanceNormalizationRecordConverter",
    "BandProvenanceNormalizationRecordSourceDeviceProfile",
    "BandProvenanceNormalizationRecordSourceFile",
    "BandProvenanceNormalizationRecordSourceFileBand",
    "BandProvenanceNormalizationRef",
    "BandProvenanceZarrSeal",
    "BandProvenanceZarrSealMember",
    "CaptureSession",
    "CaptureSessionDetail",
    "CaptureSessionDetailDevice",
    "CaptureSessionDetailMedia",
    "CaptureSessionDetailMediaOriginal",
    "CaptureSessionDetailMediaProvenance",
    "CaptureSessionDetailMediaProvenanceActor",
    "CaptureSessionDetailSpot",
    "CaptureSessionMedia",
    "CaptureSessionMediaOriginal",
    "CaptureSessionMediaProvenance",
    "CaptureSessionMediaProvenanceActor",
    "CaptureSessionSpot",
    "CaptureSessionTag",
    "CompleteImageUploadResponse",
    "Component",
    "CreatedSpot",
    "Device",
    "DeviceRegistration",
    "DeviceStatus",
    "ManualActionDryRun",
    "ManualActionDryRunChecks",
    "ManualActionDryRunChecksConflict",
    "ManualActionDryRunChecksDefinition",
    "ManualActionDryRunChecksOnline",
    "ManualActionDryRunChecksSchema",
    "ManualActionDryRunChecksScope",
    "ManualActionExecution",
    "MediaAsset",
    "MediaAssetOriginal",
    "MediaAssetPresignedUrl",
    "MediaAssetProvenance",
    "MediaAssetProvenanceActor",
    "Organization",
    "PhenosSession",
    "PhenosSessionCreation",
    "PhenosSessionCreationCredential",
    "PhenosSessionCreationSession",
    "PhenosSessionCreationSessionReferences",
    "PhenosSessionCreationSessionReferencesAnnotation",
    "PhenosSessionCreationSessionReferencesImage",
    "PhenosSessionCreationSessionReferencesImageSourceBinding",
    "PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystem",
    "PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAngleConvention",
    "PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxes",
    "PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxesX",
    "PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemAxesY",
    "PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemDimensions",
    "PhenosSessionCreationSessionReferencesImageSourceBindingCoordinateSystemPixelOrigin",
    "PhenosSessionCreationSessionReferencesImageSourceBindingGridExifApplied",
    "PhenosSessionCreationSessionReferencesImageSourceBindingGridExifAppliedStoredDimensions",
    "PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlane",
    "PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlaneAxe",
    "PhenosSessionCreationSessionReferencesImageSourceBindingGridNativePlaneDimensions",
    "PhenosSessionCreationSessionReferencesImageSourceBindingPlane",
    "PhenosSessionCreationSessionReferencesImageSourceBindingPlaneAxisSelection",
    "PhenosSessionReferences",
    "PhenosSessionReferencesAnnotation",
    "PhenosSessionReferencesImage",
    "PhenosSessionReferencesImageSourceBinding",
    "PhenosSessionReferencesImageSourceBindingCoordinateSystem",
    "PhenosSessionReferencesImageSourceBindingCoordinateSystemAngleConvention",
    "PhenosSessionReferencesImageSourceBindingCoordinateSystemAxes",
    "PhenosSessionReferencesImageSourceBindingCoordinateSystemAxesX",
    "PhenosSessionReferencesImageSourceBindingCoordinateSystemAxesY",
    "PhenosSessionReferencesImageSourceBindingCoordinateSystemDimensions",
    "PhenosSessionReferencesImageSourceBindingCoordinateSystemPixelOrigin",
    "PhenosSessionReferencesImageSourceBindingGridExifApplied",
    "PhenosSessionReferencesImageSourceBindingGridExifAppliedStoredDimensions",
    "PhenosSessionReferencesImageSourceBindingGridNativePlane",
    "PhenosSessionReferencesImageSourceBindingGridNativePlaneAxe",
    "PhenosSessionReferencesImageSourceBindingGridNativePlaneDimensions",
    "PhenosSessionReferencesImageSourceBindingPlane",
    "PhenosSessionReferencesImageSourceBindingPlaneAxisSelection",
    "RecipeBatchCancel",
    "RecipeBatchPage",
    "RecipeBatchPageCounts",
    "RecipeBatchPageRow",
    "RecipeBatchPageRowMetricsValue",
    "RecipeBatchPageRowScale",
    "RecipeBatchPageRowTag",
    "RecipeDetail",
    "RecipeDetailDefinition",
    "RecipeDetailDefinitionSlotAnnotations",
    "RecipeDetailDefinitionSlotAnnotationsSelectAll",
    "RecipeDetailDefinitionSlotAnnotationsSelectTag",
    "RecipeDetailDefinitionSlotPhoto",
    "RecipeDetailDefinitionStep",
    "RecipeDetailDefinitionStepInputsValue",
    "RecipeDetailVersion",
    "RecipeDetailVersionBasisCountOnly",
    "RecipeDetailVersionBasisReadable",
    "RecipeDetailVersionBasisReadableEntry",
    "RecipeDetailVersionContextHidden",
    "RecipeDetailVersionContextNone",
    "RecipeDetailVersionContextPhoto",
    "RecipeDetailVersionDefinition",
    "RecipeDetailVersionDefinitionSlotAnnotations",
    "RecipeDetailVersionDefinitionSlotAnnotationsSelectAll",
    "RecipeDetailVersionDefinitionSlotAnnotationsSelectTag",
    "RecipeDetailVersionDefinitionSlotPhoto",
    "RecipeDetailVersionDefinitionStep",
    "RecipeDetailVersionDefinitionStepInputsValue",
    "RecipeList",
    "RecipeListRecipe",
    "RecipeListRecipeDefinition",
    "RecipeListRecipeDefinitionSlotAnnotations",
    "RecipeListRecipeDefinitionSlotAnnotationsSelectAll",
    "RecipeListRecipeDefinitionSlotAnnotationsSelectTag",
    "RecipeListRecipeDefinitionSlotPhoto",
    "RecipeListRecipeDefinitionStep",
    "RecipeListRecipeDefinitionStepInputsValue",
    "RecipeRun",
    "RecipeRunAgain",
    "RecipeRunAgainRun",
    "RecipeRunStart",
    "RecipeRunStartRun",
    "RecipeRunStep",
    "RecipeRunStepOutput",
    "RecipeRunStepOutputMetricsValue",
    "RecipeRunStepOutputProvenance",
    "RecipeRunStepOutputProvenanceCodec",
    "RecipeSummary",
    "RecipeSummaryDefinition",
    "RecipeSummaryDefinitionSlotAnnotations",
    "RecipeSummaryDefinitionSlotAnnotationsSelectAll",
    "RecipeSummaryDefinitionSlotAnnotationsSelectTag",
    "RecipeSummaryDefinitionSlotPhoto",
    "RecipeSummaryDefinitionStep",
    "RecipeSummaryDefinitionStepInputsValue",
    "Rule",
    "RuleAction",
    "RuleActionActionDefinition",
    "RuleActionActionDefinitionNameTranslation",
    "RuleActionCaptureSessionOptions",
    "RuleExecution",
    "RuleExecutionActionsExecuted",
    "RuleExecutionRule",
    "RuleTriggerConfigCondition",
    "RuleTriggerConfigCron",
    "RuleTriggerConfigEvent",
    "Spot",
    "SpotAgent",
    "SpotAgentDevice",
    "SpotAgentRealtimeStatus",
    "SpotAgentRealtimeStatusHealth",
    "SpotAgentsSummary",
    "SpotAgentsSummaryAvgHealth",
    "SpotDeviceStats",
    "SpotGroup",
    "SpotGroupParent",
    "SpotStructure",
    "SpotStructureDevice",
    "SpotStructureDeviceAction",
    "SpotStructureDeviceActionMetadata",
    "SpotStructureDeviceActionMetadataUi",
    "SpotStructureDeviceActionNameTranslation",
    "SpotStructureDeviceComponent",
    "SpotStructureDeviceComponentAction",
    "SpotStructureDeviceComponentActionMetadata",
    "SpotStructureDeviceComponentActionMetadataUi",
    "SpotStructureDeviceComponentActionNameTranslation",
    "SpotStructureDeviceComponentTopic",
    "SpotStructureDeviceComponentTopicMetadata",
    "SpotStructureDeviceComponentTopicMetadataStateMappingValue",
    "SpotStructureDeviceTopic",
    "SpotStructureDeviceTopicMetadata",
    "SpotStructureDeviceTopicMetadataStateMappingValue",
    "SpotStructureRule",
    "SpotStructureRuleAction",
    "SpotStructureRuleActionActionDefinition",
    "SpotStructureRuleActionActionDefinitionNameTranslation",
    "SpotStructureRuleActionCaptureSessionOptions",
    "SpotStructureRuleTriggerConfigCondition",
    "SpotStructureRuleTriggerConfigCron",
    "SpotStructureRuleTriggerConfigEvent",
    "SpotStructureSpot",
    "SpotStructureStats",
    "SpotTag",
    "Telemetry",
    "TelemetryBatch",
    "TelemetryBatchExport",
    "TelemetryBatchRollup",
    "TelemetryTopics",
    "UploadImageResponse",
    "ZarrFiles",
]
