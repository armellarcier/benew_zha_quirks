"""Custom Sonoff TRVZB quirk with persistent calibration."""
from zigpy.quirks import CustomCluster
from zigpy.quirks.v2 import QuirkBuilder, NumberDeviceClass
from zigpy.quirks.v2.homeassistant import UnitOfTemperature
import zigpy.types as t
from zigpy.zcl.foundation import BaseAttributeDefs, ZCLAttributeDef
from zigpy.zcl import foundation
import logging

_LOGGER = logging.getLogger(__name__)


class CustomSonoffCluster(CustomCluster):
    """Custom Sonoff cluster with persistent calibration."""

    cluster_id = 0xFC11

    class AttributeDefs(BaseAttributeDefs):
        child_lock = ZCLAttributeDef(id=0x0000, type=t.Bool)
        open_window = ZCLAttributeDef(id=0x6000, type=t.Bool)
        frost_protection_temperature = ZCLAttributeDef(id=0x6002, type=t.int16s)
        idle_steps = ZCLAttributeDef(id=0x6003, type=t.uint16_t, access="r")
        closing_steps = ZCLAttributeDef(id=0x6004, type=t.uint16_t, access="r")
        valve_opening_limit_voltage = ZCLAttributeDef(id=0x6005, type=t.uint16_t, access="r")
        valve_closing_limit_voltage = ZCLAttributeDef(id=0x6006, type=t.uint16_t, access="r")
        valve_motor_running_voltage = ZCLAttributeDef(id=0x6007, type=t.uint16_t, access="r")
        valve_opening_degree = ZCLAttributeDef(id=0x600B, type=t.uint8_t)
        valve_closing_degree = ZCLAttributeDef(id=0x600C, type=t.uint8_t)
        external_temperature_sensor_enable = ZCLAttributeDef(id=0x600E, type=t.uint8_t)
        external_temperature_sensor_value = ZCLAttributeDef(id=0x600D, type=t.int16s)
        temperature_control_accuracy = ZCLAttributeDef(id=0x6011, type=t.int16s)
        
        # Attributs virtuels pour calibration
        valve_min_limit = ZCLAttributeDef(id=0x7000, type=t.uint8_t)
        valve_max_limit = ZCLAttributeDef(id=0x7001, type=t.uint8_t)
        virtual_valve_position = ZCLAttributeDef(id=0x7002, type=t.uint8_t)

    @property
    def _is_manuf_specific(self):
        return False

    def __init__(self, *args, **kwargs):
        """Initialize with default values."""
        super().__init__(*args, **kwargs)
        
        # Valeurs par défaut
        self._valve_min_limit = 0
        self._valve_max_limit = 100
        
        # Initialiser le cache
        self._attr_cache[0x7000] = self._valve_min_limit
        self._attr_cache[0x7001] = self._valve_max_limit
        self._attr_cache[0x7002] = 0
        
        _LOGGER.debug(
            f"Initialized calibration for {self.endpoint.device.ieee}: "
            f"min={self._valve_min_limit}%, max={self._valve_max_limit}%"
        )

    async def write_attributes(self, attributes, manufacturer=None):
        """Intercept writes to handle virtual attributes."""
        processed_attrs = {}
        
        for attr_id, value in attributes.items():
            if isinstance(attr_id, str):
                attr_id = self.attributes_by_name[attr_id].id
            
            if attr_id == 0x7002:  # virtual_valve_position
                real_value = self._virtual_to_real(value)
                processed_attrs[0x600B] = real_value
                processed_attrs[0x600C] = 100 - real_value
                
                # Notifier HA du changement
                self._update_attribute(0x7002, value)
                
                _LOGGER.debug(
                    f"Virtual {value}% → Real {real_value}% "
                    f"(limits: {self._valve_min_limit}-{self._valve_max_limit}%)"
                )
                
            elif attr_id == 0x7000:  # valve_min_limit
                self._valve_min_limit = value
                # Notifier HA pour persistance
                self._update_attribute(0x7000, value)
                _LOGGER.info(f"Set valve min limit to {value}%")
                
            elif attr_id == 0x7001:  # valve_max_limit
                self._valve_max_limit = value
                # Notifier HA pour persistance
                self._update_attribute(0x7001, value)
                _LOGGER.info(f"Set valve max limit to {value}%")
                
            else:
                processed_attrs[attr_id] = value
        
        if processed_attrs:
            return await super().write_attributes(processed_attrs, manufacturer)
        
        return [[foundation.WriteAttributesStatusRecord(foundation.Status.SUCCESS)]]

    async def read_attributes(self, attributes, manufacturer=None):
        """Intercept reads to handle virtual attributes."""
        virtual_attrs = {0x7000, 0x7001, 0x7002}
        real_attrs = [a for a in attributes if a not in virtual_attrs]
        
        result = []
        if real_attrs:
            result = await super().read_attributes(real_attrs, manufacturer)
        
        for attr_id in attributes:
            if attr_id in virtual_attrs:
                value = self._attr_cache.get(attr_id, 0)
                result.append(
                    foundation.ReadAttributeRecord(
                        attr_id, foundation.Status.SUCCESS, 
                        foundation.TypeValue(type=t.uint8_t, value=value)
                    )
                )
        
        return result

    def _virtual_to_real(self, virtual_pos):
        """Convert virtual position (0-100) to real position (min-max)."""
        if self._valve_max_limit == self._valve_min_limit:
            return self._valve_min_limit
        
        if virtual_pos == 0:
            return 0

        if virtual_pos == 100:
            return 100
        
        real = self._valve_min_limit + (virtual_pos / 100) * (
            self._valve_max_limit - self._valve_min_limit
        )
        return max(self._valve_min_limit, min(int(real), self._valve_max_limit))

    def _real_to_virtual(self, real_pos):
        """Convert real position to virtual position (0-100)."""
        if self._valve_max_limit == self._valve_min_limit:
            return 0
        
        virtual = ((real_pos - self._valve_min_limit) * 100) / (
            self._valve_max_limit - self._valve_min_limit
        )
        return max(0, min(int(virtual), 100))

    def _update_attribute(self, attrid, value):
        """Override to sync and persist virtual attributes."""
        # Mettre à jour le cache
        self._attr_cache[attrid] = value
        
        # Synchroniser les limites internes
        if attrid == 0x7000:
            self._valve_min_limit = value
        elif attrid == 0x7001:
            self._valve_max_limit = value
        elif attrid == 0x600B:  # valve_opening_degree
            # Mettre à jour la position virtuelle
            virtual = self._real_to_virtual(value)
            if self._attr_cache.get(0x7002) != virtual:
                self._attr_cache[0x7002] = virtual
                # Appeler parent pour notifier HA
                super()._update_attribute(0x7002, virtual)
                return  # Éviter double notification
        
        # Notifier HA du changement (pour persistance)
        super()._update_attribute(attrid, value)


# Enregistrer le quirk
(
    QuirkBuilder("SONOFF", "TRVZB")
    .replaces(CustomSonoffCluster)
    .number(
        "virtual_valve_position",
        CustomSonoffCluster.cluster_id,
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        translation_key="virtual_valve_position",
        fallback_name="Valve Position",
    )
    .number(
        "valve_min_limit",
        CustomSonoffCluster.cluster_id,
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        translation_key="valve_min_limit",
        fallback_name="Valve Min Limit (%)",
    )
    .number(
        "valve_max_limit",
        CustomSonoffCluster.cluster_id,
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        translation_key="valve_max_limit",
        fallback_name="Valve Max Limit (%)",
    )
    .switch(
        CustomSonoffCluster.AttributeDefs.child_lock.name,
        CustomSonoffCluster.cluster_id,
        translation_key="child_lock",
        fallback_name="Child lock",
    )
    .switch(
        CustomSonoffCluster.AttributeDefs.open_window.name,
        CustomSonoffCluster.cluster_id,
        translation_key="open_window",
        fallback_name="Open window",
    )
    .switch(
        CustomSonoffCluster.AttributeDefs.external_temperature_sensor_enable.name,
        CustomSonoffCluster.cluster_id,
        translation_key="external_temperature_sensor",
        fallback_name="External temperature sensor",
    )
    .number(
        CustomSonoffCluster.AttributeDefs.frost_protection_temperature.name,
        CustomSonoffCluster.cluster_id,
        min_value=4.0,
        max_value=35.0,
        step=0.5,
        unit=UnitOfTemperature.CELSIUS,
        multiplier=0.01,
        translation_key="frost_protection_temperature",
        fallback_name="Frost protection temperature",
    )
    .number(
        CustomSonoffCluster.AttributeDefs.temperature_control_accuracy.name,
        CustomSonoffCluster.cluster_id,
        min_value=-1.0,
        max_value=-0.2,
        step=0.2,
        device_class=NumberDeviceClass.TEMPERATURE,
        unit=UnitOfTemperature.CELSIUS,
        multiplier=0.01,
        translation_key="temperature_control_accuracy",
        fallback_name="Temperature control accuracy",
    )
    .number(
        CustomSonoffCluster.AttributeDefs.external_temperature_sensor_value.name,
        CustomSonoffCluster.cluster_id,
        min_value=0.0,
        max_value=99.9,
        step=0.1,
        device_class=NumberDeviceClass.TEMPERATURE,
        unit=UnitOfTemperature.CELSIUS,
        multiplier=0.01,
        translation_key="external_temperature_sensor_value",
        fallback_name="External temperature sensor value",
    )
    
    # Position réelle (pour debug, désactivée par défaut)
    .number(
        CustomSonoffCluster.AttributeDefs.valve_opening_degree.name,
        CustomSonoffCluster.cluster_id,
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        translation_key="valve_opening_degree",
        fallback_name="Valve opening degree",
        initially_disabled=False,
    )
    .number(
        CustomSonoffCluster.AttributeDefs.valve_closing_degree.name,
        CustomSonoffCluster.cluster_id,
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        translation_key="valve_closing_degree",
        fallback_name="Valve closing degree",
        initially_disabled=False,
    )
    
    .add_to_registry()
)

